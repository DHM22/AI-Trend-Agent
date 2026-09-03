"""
Curriculum Ingestion -> Chroma (RAG source for the CurriculumAgent)
====================================================================
Handles BOTH .pptx and .pdf slide decks, since WeCloudData gives us a mix.
Do NOT convert PPTX to PDF first -- that loses speaker notes and table
structure, and adds a step that can only degrade quality.

Expected layout (matches the bootcamp's required repo structure):

    01_data/curriculum/
      week_01/
        Intro_to_Agents.pptx
        Python_and_APIs.pdf
      week_02/
        RAG_Introduction.pptx
      week_03/          <- empty until materials are released
      ...

The WEEK comes from the folder name, not the filename. That is deliberate:
filenames get renamed ("RAG_intro_FINAL_v2.pptx") but folders don't. The
topic still comes from the filename, which is fine -- descriptive, not
structural.

Design goal: incremental. Drop a new week's slides in, re-run, the store
grows. Existing chunks are upserted by stable ID, never duplicated.

Usage:
    python curriculum_ingest.py --curriculum 01_data/curriculum --db ./vectorstore
    python curriculum_ingest.py --db ./vectorstore --query "LangChain agents"
    python curriculum_ingest.py --db ./vectorstore --query "chunking" --week 2

Embeddings: uses Chroma's built-in local model by default (no API key, free).
Swap to OpenAI embeddings for better quality -- see EMBEDDING NOTE at bottom.
"""

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from pptx import Presentation
import pdfplumber


# ---------------------------------------------------------------------------
# SCHEMA -- one chunk of curriculum text plus where it came from.
# The metadata is what makes recommendations citable:
#   "Week 2, RAG Introduction, slide 25"  not  "the curriculum mentions RAG"
# ---------------------------------------------------------------------------

@dataclass
class CurriculumChunk:
    text: str
    week: int | None      # 2                    (from the week_02/ folder)
    topic: str            # "RAG Introduction"   (from the filename)
    source_file: str      # "RAG_Introduction.pptx"
    slide_number: int     # 25
    chunk_index: int = 0  # >0 if one slide was split into several chunks

    @property
    def chunk_id(self) -> str:
        """Stable ID so re-running ingestion updates rather than duplicates."""
        raw = f"{self.week}:{self.source_file}:{self.slide_number}:{self.chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    @property
    def citation(self) -> str:
        wk = f"Week {self.week}" if self.week is not None else "Uncategorised"
        return f"{wk} / {self.topic} / slide {self.slide_number}"


# ---------------------------------------------------------------------------
# PATH PARSING
# ---------------------------------------------------------------------------

WEEK_DIR = re.compile(r"^week[_\-]?(\d+)$", re.IGNORECASE)


def week_from_path(path: Path, root: Path) -> int | None:
    """
    Walk up from the file toward the curriculum root looking for week_NN.
    Returns None for files dropped outside a week folder -- they still get
    ingested, just without a week for filtering.
    """
    for parent in path.relative_to(root).parents:
        if parent.name:
            m = WEEK_DIR.match(parent.name)
            if m:
                return int(m.group(1))
    return None


def topic_from_filename(path: Path) -> str:
    """RAG_Introduction_Part_1.pptx -> 'RAG Introduction Part 1'"""
    return re.sub(r"[_\-]+", " ", path.stem).strip()


# ---------------------------------------------------------------------------
# EXTRACTION -- one function per format, both return the same shape.
# ---------------------------------------------------------------------------

def extract_pptx(path: Path, week: int | None) -> list[CurriculumChunk]:
    """Pull text from every shape on every slide, including speaker notes."""
    prs = Presentation(str(path))
    topic = topic_from_filename(path)
    chunks: list[CurriculumChunk] = []

    for i, slide in enumerate(prs.slides, start=1):
        parts: list[str] = []

        for shape in slide.shapes:
            # tables hold real content in course decks -- don't skip them
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())

        # speaker notes often explain the concept better than the slide itself
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                parts.append(f"[Speaker notes] {notes}")

        text = "\n".join(parts).strip()
        if text:
            chunks.append(CurriculumChunk(
                text=text, week=week, topic=topic,
                source_file=path.name, slide_number=i))

    return chunks


def extract_pdf(path: Path, week: int | None) -> list[CurriculumChunk]:
    """Pull text page by page. Each PDF page == one slide."""
    topic = topic_from_filename(path)
    chunks: list[CurriculumChunk] = []

    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                chunks.append(CurriculumChunk(
                    text=text, week=week, topic=topic,
                    source_file=path.name, slide_number=i))

    return chunks


def extract_all(curriculum_root: Path) -> list[CurriculumChunk]:
    """
    Recursively walk the curriculum tree, routing each file to the right
    extractor and tagging it with the week from its folder.
    """
    chunks: list[CurriculumChunk] = []
    skipped: list[str] = []
    image_only: list[str] = []

    for path in sorted(curriculum_root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue

        week = week_from_path(path, curriculum_root)
        suffix = path.suffix.lower()

        if suffix == ".pptx":
            found = extract_pptx(path, week)
        elif suffix == ".pdf":
            found = extract_pdf(path, week)
        else:
            skipped.append(path.name)
            continue

        if not found:
            # no extractable text at all -- almost certainly a scan or an
            # all-image deck. This is the failure mode worth catching early.
            image_only.append(str(path.relative_to(curriculum_root)))
        chunks.extend(found)

    if skipped:
        print(f"  ! skipped unsupported files: {', '.join(skipped)}")
    if image_only:
        print(f"  !! NO TEXT EXTRACTED from: {', '.join(image_only)}")
        print("     Likely image-only slides. Text RAG cannot see them.")

    return chunks


# ---------------------------------------------------------------------------
# CHUNKING -- split long slides so retrieval stays precise.
# A whole dense slide as one chunk buries the relevant sentence.
# ---------------------------------------------------------------------------

MIN_CHARS = 50


def drop_thin_chunks(chunks: list[CurriculumChunk],
                     min_chars: int = MIN_CHARS) -> tuple[list[CurriculumChunk], int]:
    """
    Remove section dividers and title-only slides ("Vector DB | RAG",
    "01 Preamble", "Questions?").

    These are actively harmful, not just useless: a title slide is almost
    entirely topic keywords, so it scores high on any query about that topic
    and crowds out the substantive slide underneath. Measured on real course
    decks, ~19% of pages were under this threshold.
    """
    kept = [c for c in chunks if len(c.text) >= min_chars]
    return kept, len(chunks) - len(kept)


def split_long_chunks(chunks: list[CurriculumChunk],
                      max_chars: int = 1200,
                      overlap: int = 150) -> list[CurriculumChunk]:
    """~1200 chars is roughly 300 tokens. Overlap avoids cutting mid-concept."""
    out: list[CurriculumChunk] = []

    for chunk in chunks:
        if len(chunk.text) <= max_chars:
            out.append(chunk)
            continue

        start, idx = 0, 0
        while start < len(chunk.text):
            out.append(CurriculumChunk(
                text=chunk.text[start:start + max_chars],
                week=chunk.week, topic=chunk.topic,
                source_file=chunk.source_file,
                slide_number=chunk.slide_number, chunk_index=idx))
            start += max_chars - overlap
            idx += 1

    return out


# ---------------------------------------------------------------------------
# VECTOR STORE
# ---------------------------------------------------------------------------

COLLECTION = "wecloud_curriculum"


def get_collection(db_path: str, embedding_function=None):
    """
    embedding_function=None uses Chroma's built-in local model (free, no key).
    Pass the SAME function to ingest and query, or results are meaningless.
    """
    client = chromadb.PersistentClient(path=db_path)
    kwargs = {"name": COLLECTION, "metadata": {"hnsw:space": "cosine"}}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    return client.get_or_create_collection(**kwargs)


def ingest(curriculum_root: str, db_path: str, embedding_function=None) -> int:
    root = Path(curriculum_root)
    if not root.is_dir():
        raise SystemExit(f"curriculum folder not found: {curriculum_root}")

    print(f"reading {curriculum_root} ...")
    raw = extract_all(root)

    # coverage per week -- tells you at a glance what is actually indexed
    by_week: dict[str, int] = {}
    for c in raw:
        key = f"week_{c.week:02d}" if c.week is not None else "uncategorised"
        by_week[key] = by_week.get(key, 0) + 1
    for wk in sorted(by_week):
        print(f"    {wk}: {by_week[wk]} slides")

    kept, dropped = drop_thin_chunks(raw)
    if dropped:
        print(f"  dropped {dropped} title/divider slides under {MIN_CHARS} chars")

    chunks = split_long_chunks(kept)
    print(f"  {len(raw)} slides -> {len(chunks)} chunks")

    if not chunks:
        print("  nothing to ingest.")
        return 0

    collection = get_collection(db_path, embedding_function)

    # upsert (not add) so re-running is safe and incremental
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[{
            "week": c.week if c.week is not None else -1,   # Chroma rejects None
            "topic": c.topic,
            "source_file": c.source_file,
            "slide_number": c.slide_number,
        } for c in chunks],
    )

    print(f"  stored -> {db_path} ({collection.count()} chunks total)")
    return len(chunks)


# ---------------------------------------------------------------------------
# HYBRID SEARCH
# Embeddings blur rare identifiers. Measured on real decks: a query for
# "FAISS" returned nothing, even though 3 slides contain the literal word --
# MiniLM has no useful representation for a rare acronym, so the similarity
# score is close to noise.
#
# GitHub release notes are full of exactly these tokens (AgentExecutor,
# create_agent, @tool, FAISS), so this is the common case for us, not an
# edge case. Fix: run the semantic search, then a literal substring search
# for any rare identifiers in the query, and merge.
# ---------------------------------------------------------------------------

# words that look like identifiers, not prose:
#   FAISS, RAG, PEFT        -> all-caps acronyms (2+ chars)
#   AgentExecutor, LangChain -> CamelCase
#   create_agent, text_splitter -> snake_case
#   @tool, .from_documents  -> punctuation-prefixed
IDENTIFIER = re.compile(
    r"\b[A-Z]{2,}\b"                    # FAISS, RAG, LLM
    r"|\b[a-z]+_[a-z_]+\b"              # create_agent
    r"|\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b" # AgentExecutor, LangChain
    r"|@[a-zA-Z_]+"                     # @tool
)

# acronyms too common in this domain to be useful as exact-match signals --
# they appear on dozens of slides and would swamp the semantic results
STOP_IDENTIFIERS = {"AI", "ML", "API", "LLM", "LLMS", "GPU", "CPU", "PDF", "JSON",
                    "HTTP", "URL", "OK", "ID", "UI", "OS", "IT", "US"}


def extract_identifiers(question: str) -> list[str]:
    """Pull out rare technical tokens worth searching for literally."""
    found = IDENTIFIER.findall(question)
    return [t for t in dict.fromkeys(found) if t.upper() not in STOP_IDENTIFIERS]


def _row_to_hit(doc, meta, similarity: float, exact_match: str | None) -> dict:
    wk = meta["week"] if meta["week"] != -1 else None
    return {
        "text": doc,
        "week": wk,
        "topic": meta["topic"],
        "source_file": meta["source_file"],
        "slide_number": meta["slide_number"],
        "similarity": similarity,
        "exact_match": exact_match,     # the identifier found, or None
        "citation": (f"Week {wk}" if wk else "Uncategorised")
                    + f" / {meta['topic']} / slide {meta['slide_number']}",
    }


def query(db_path: str, question: str, k: int = 3,
          week: int | None = None, embedding_function=None,
          hybrid: bool = True) -> list[dict]:
    """
    This is what CurriculumAgent calls. Returns chunks WITH citations.

    week=N restricts the search to one week's material.
    hybrid=False disables the literal identifier pass (semantic only).

    Hits carry an "exact_match" field: the identifier literally found in the
    slide, or None for purely semantic matches. Exact matches are ranked
    first -- if a slide literally contains "FAISS", it is relevant to a FAISS
    question regardless of what the embedding distance says. Callers should
    treat exact_match hits as clearing RELEVANCE_FLOOR automatically, since
    embedding similarity is not meaningful for these.
    """
    collection = get_collection(db_path, embedding_function)
    total = collection.count()
    if total == 0:
        return []

    where = {"week": week} if week is not None else None

    # --- pass 1: semantic
    kwargs = {"query_texts": [question], "n_results": min(k, total)}
    if where:
        kwargs["where"] = where
    res = collection.query(**kwargs)

    hits: list[dict] = []
    seen: set[tuple] = set()

    if res["documents"] and res["documents"][0]:
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            key = (meta["source_file"], meta["slide_number"])
            seen.add(key)
            hits.append(_row_to_hit(doc, meta, round(1 - dist, 3), None))

    # --- pass 2: literal identifier lookup
    if hybrid:
        for token in extract_identifiers(question):
            g_kwargs = {"where_document": {"$contains": token}, "limit": k}
            if where:
                g_kwargs["where"] = where
            found = collection.get(**g_kwargs)

            for doc, meta in zip(found["documents"], found["metadatas"]):
                key = (meta["source_file"], meta["slide_number"])
                if key in seen:
                    # already returned semantically -- just tag it as exact
                    for h in hits:
                        if (h["source_file"], h["slide_number"]) == key:
                            h["exact_match"] = token
                    continue
                seen.add(key)
                hits.append(_row_to_hit(doc, meta, None, token))

    # exact matches first, then by descending similarity
    hits.sort(key=lambda h: (h["exact_match"] is None, -(h["similarity"] or 0)))
    return hits[:k]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Ingest course slides into Chroma")
    ap.add_argument("--curriculum", default="01_data/curriculum",
                    help="root folder containing week_NN/ subfolders")
    ap.add_argument("--db", default="./vectorstore", help="Chroma persistence path")
    ap.add_argument("--query", help="skip ingestion, just search the existing store")
    ap.add_argument("--week", type=int, help="restrict a query to one week")
    ap.add_argument("-k", type=int, default=3, help="results to return")
    args = ap.parse_args()

    if args.query:
        hits = query(args.db, args.query, args.k, week=args.week)
        if not hits:
            print("no results -- has anything been ingested?")
            return
        for h in hits:
            score = f"{h['similarity']}" if h["similarity"] is not None else "exact"
            tag = f"  <- literal '{h['exact_match']}'" if h["exact_match"] else ""
            print(f"\n[{score}] {h['citation']}{tag}")
            print(f"  {h['text'][:200]}...")
    else:
        ingest(args.curriculum, args.db)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# EMBEDDING NOTE
# ---------------------------------------------------------------------------
# Chroma's default embedding model runs locally and costs nothing -- fine for
# development. For the final demo, OpenAI embeddings retrieve noticeably better
# on technical text. To switch:
#
#   from chromadb.utils import embedding_functions
#   ef = embedding_functions.OpenAIEmbeddingFunction(
#           api_key=os.environ["OPENAI_API_KEY"],
#           model_name="text-embedding-3-small")
#   client.get_or_create_collection(name=COLLECTION, embedding_function=ef)
#
# Pass the SAME embedding_function on both ingest and query, or results are
# meaningless. If you switch models, DELETE the vectorstore folder and
# re-ingest -- otherwise Chroma errors on mismatched embedding dimensions.
#
# ---------------------------------------------------------------------------
# IMAGE-ONLY SLIDES
# ---------------------------------------------------------------------------
# If ingestion reports "NO TEXT EXTRACTED" for a deck, its content lives in
# diagrams that text extraction cannot see. Options, cheapest first:
#   1. Accept it and document the gap (fine for an MVP).
#   2. Hand-write a short description per diagram slide into a .txt beside it.
#   3. Send slide images to a vision model and store the description.
# Do NOT build option 3 first -- get text RAG working, then decide whether the
# missing diagrams actually hurt retrieval quality.
