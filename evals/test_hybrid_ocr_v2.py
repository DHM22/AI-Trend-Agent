import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "02_src" / "curriculum_ingest.py"
SPEC = importlib.util.spec_from_file_location("curriculum_ingest", MODULE_PATH)
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)


class FakePage:
    width = 100
    height = 100

    def __init__(self, images=None, lines=None, rects=None, curves=None):
        self.images = images or []
        self.lines = lines or []
        self.rects = rects or []
        self.curves = curves or []


def image_box(x0=10, top=10, x1=70, bottom=70):
    return {"x0": x0, "top": top, "x1": x1, "bottom": bottom}


class HybridOcrV2Tests(unittest.TestCase):
    def test_ocr_triggers_for_sparse_native_text(self):
        self.assertTrue(ingest._should_ocr_pdf_page(FakePage(), "short"))

    def test_ocr_triggers_for_embedded_visual_with_dense_text(self):
        page = FakePage(images=[image_box()])
        self.assertTrue(ingest._should_ocr_pdf_page(page, "x" * 500))
        self.assertEqual(ingest._embedded_visual_regions(page),
                         [(10.0, 10.0, 70.0, 70.0)])

    def test_tiny_logo_and_full_page_background_do_not_trigger_dense_page(self):
        page = FakePage(images=[image_box(0, 0, 10, 10),
                                image_box(0, 0, 100, 100)])
        self.assertFalse(ingest._should_ocr_pdf_page(page, "x" * 500))

    def test_vector_heavy_page_triggers_ocr(self):
        page = FakePage(lines=[{}] * ingest.OCR_VECTOR_MARK_THRESHOLD)
        self.assertTrue(ingest._should_ocr_pdf_page(page, "x" * 500))

    def test_overlapping_image_regions_are_deduplicated(self):
        page = FakePage(images=[image_box(), image_box(11, 11, 71, 71)])
        self.assertEqual(len(ingest._embedded_visual_regions(page)), 1)

    def test_merge_preserves_both_sources_and_deduplicates_overlap(self):
        native = "Title\nShared line\nNative-only sentence"
        ocr = "Shared   line\nOCR-only diagram label"
        merged, provenance = ingest._merge_extracted_text_with_provenance(
            native, ocr)
        self.assertEqual(merged.count("Shared line"), 1)
        self.assertIn("Native-only sentence", merged)
        self.assertIn("OCR-only diagram label", merged)
        self.assertEqual(provenance, "hybrid")

    def test_unicode_cleaning_repairs_known_artifacts(self):
        dirty = "â€œquotedâ€ â€” value Â° آ°\n==========\nA   B"
        cleaned = ingest._normalize_extracted_text(dirty)
        self.assertEqual(cleaned, "“quoted” — value ° °\n===\nA B")

    def test_technical_identifiers_are_preserved_exactly(self):
        identifiers = (
            'get_stock_price(ticker="NVDA") LangChain==0.3.7 '
            'create_agent @tool package_name-v2.1.0'
        )
        self.assertEqual(ingest._normalize_extracted_text(identifiers), identifiers)

    def test_provenance_and_content_type_survive_chunk_splitting(self):
        chunk = ingest.CurriculumChunk(
            text="identifier " * 200,
            week=3,
            topic="Hybrid OCR",
            source_file="fixture.pdf",
            slide_number=7,
            content_type="slides",
            extraction_provenance="hybrid",
        )
        parts = ingest.split_long_chunks([chunk], max_chars=100, overlap=10)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(part.content_type == "slides" for part in parts))
        self.assertTrue(all(part.extraction_provenance == "hybrid" for part in parts))


if __name__ == "__main__":
    unittest.main()
