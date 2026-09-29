"""
Confound check for test_signals_graded_v2.json.
================================================
Verifies that NO single observable input field separates genuine from
fabricated -- i.e. the source-tier shortcut (and every other one-field rule) is
broken. For each field it reports the best accuracy a "map each value to its
majority class" rule could reach; a field that reaches 100% fully separates the
classes and is a leak.

    python 04_eval/check_v2_confounds.py [path]

Only INPUT fields the verifier can see are tested -- never the gold labels
themselves (those define the label and are expected to correlate).
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent / "data" / "test_signals_graded_v2.json"

_REPO_RE = re.compile(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*")


def features(item: dict, event_counts: Counter) -> dict:
    title = item.get("title") or ""
    url = item.get("url") or ""
    summary = item.get("summary") or ""
    event_id = item.get("gold", {}).get("event_id")
    has_repo = bool(_REPO_RE.search(title)) or "github.com" in url
    return {
        "source_tier": item.get("source_tier"),
        "source": item.get("source"),
        "url_present": bool(url.strip()),
        "names_repo": has_repo,
        "multi_source": event_counts.get(event_id, 0) > 1,
        "split": item.get("split"),
        "published_present": bool((item.get("published") or "").strip()),
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    n = len(items)
    labels = [bool(it["gold"]["is_genuine"]) for it in items]
    genuine = sum(labels)
    event_counts = Counter(it.get("gold", {}).get("event_id") for it in items)

    print(f"dataset: {path}")
    print(f"items: {n}  genuine: {genuine}  fabricated: {n - genuine}")
    baseline = max(genuine, n - genuine) / n
    print(f"majority-class baseline accuracy: {baseline:.1%}\n")

    feats = [features(it, event_counts) for it in items]
    fields = list(feats[0].keys())

    print(f"{'field':16} {'best 1-field acc':>16}  {'fully separates?':>16}  detail")
    print("-" * 88)
    leaks = []
    for f in fields:
        by_val = defaultdict(lambda: [0, 0])  # value -> [genuine, fabricated]
        for fe, lab in zip(feats, labels):
            by_val[fe[f]][0 if lab else 1] += 1
        # best accuracy of "map each value to its majority class"
        correct = sum(max(g, b) for g, b in by_val.values())
        acc = correct / n
        separates = abs(acc - 1.0) < 1e-9
        if separates:
            leaks.append(f)
        # show any value that is class-pure (all one label), with its size
        pure = [(v, ("genuine" if g else "fabricated"), g + b)
                for v, (g, b) in by_val.items() if (g == 0) != (b == 0)]
        pure_txt = "; ".join(f"{v}->{cls}({size})" for v, cls, size in sorted(pure, key=lambda x: -x[2])) or "none pure"
        print(f"{f:16} {acc:>15.1%}  {('YES -- LEAK' if separates else 'no'):>16}  {pure_txt[:60]}")

    print()
    if leaks:
        print(f"FAIL: these fields fully separate the classes: {leaks}")
        return 1
    # also flag near-perfect single-field rules as a softer warning
    warns = []
    for f in fields:
        by_val = defaultdict(lambda: [0, 0])
        for fe, lab in zip(feats, labels):
            by_val[fe[f]][0 if lab else 1] += 1
        acc = sum(max(g, b) for g, b in by_val.values()) / n
        if acc >= 0.9:
            warns.append((f, acc))
    if warns:
        print("WARN: single field(s) reach >=90% accuracy (not a hard leak, but "
              "close): " + ", ".join(f"{f} {a:.0%}" for f, a in warns))
    print("PASS: no single input field separates genuine from fabricated.")
    # split sanity: both classes present in both splits
    for sp in ("dev", "test"):
        g = sum(1 for it, lab in zip(items, labels) if it.get("split") == sp and lab)
        b = sum(1 for it, lab in zip(items, labels) if it.get("split") == sp and not lab)
        print(f"  split {sp}: genuine {g}, fabricated {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
