"""Synthetic evidence regressions; no datasets, credentials or network needed."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas import RawSignal, TrendCluster
from agents import verification as v


def signal(url, title="WidgetGraph adds durable workflow checkpoints", tier="secondary"):
    return RawSignal(title, "community", tier, "", url)


def source_facts(signals, documents):
    cluster = TrendCluster(signals[0].title, signals)
    facts = v.Facts([], [], 0, False, False, False)
    agent = v.VerificationAgent(tool_runner=lambda name, args: documents.get(args["url"], {"error": "offline"}))
    agent._check_sources(cluster, facts)
    return facts


class EvidenceTests(unittest.TestCase):
    def test_missing_first_party_page_withholds_prior_but_errors_do_not(self):
        s = signal("https://openai.com/index/synthetic-regression-example", tier="primary")
        cluster = TrendCluster(s.title, [s])
        for document, expected in (
            ({"missing": True, "status_code": 404}, .4),
            ({"missing": True, "status_code": 410}, .4),
            ({"missing": True}, .4),                  # older cached response
            ({"error": "HTTP 403"}, .6),
            ({"error": "timeout"}, .6),
            ({"text": "An article was retrieved."}, .6),
        ):
            facts = source_facts([s], {s.url: document})
            self.assertEqual(v._score(cluster, facts), expected, document)
            note = v._build_note(cluster, facts, expected)
            if expected == .4:
                self.assertIn("prior withheld", note)
                self.assertNotIn("supplies a provisional 0.60", note)

    def test_missing_redirect_is_bound_to_original_cited_url(self):
        s = signal("https://openai.com/old-path", tier="primary")
        facts = source_facts([s], {s.url: {"missing": True, "url": "https://openai.com/new-path"}})
        self.assertIn(s.url, facts.missing_source_urls)
        self.assertEqual(v._score(TrendCluster(s.title, [s]), facts), .4)

    def test_one_missing_page_does_not_cancel_another_first_party_prior(self):
        first = signal("https://openai.com/missing", tier="primary")
        other = signal("https://openai.com/available", tier="primary")
        facts = source_facts([first, other], {first.url: {"missing": True}, other.url: {"text": "An article exists."}})
        self.assertEqual(v._score(TrendCluster(first.title, [first, other]), facts), .6)
        facts.claim_verified = True
        self.assertEqual(v._score(TrendCluster(first.title, [first]), facts), .75)

    def test_curated_products_use_monitor_configuration_and_exact_version(self):
        self.assertEqual(v._curated_release(signal("", "LangGraph v7.8.9")), ("langchain-ai/langgraph", "7.8.9"))
        self.assertEqual(v._curated_release(signal("", "LangSmith SDK 7.8")), ("langchain-ai/langsmith-sdk", "7.8.0"))
        self.assertEqual(v._curated_release(signal("", "LangChain 7.8.9")), ("langchain-ai/langchain", "langchain==7.8.9"))
        self.assertEqual(v._curated_release(signal("", "Transformers 7.8.9-rc1")), ("huggingface/transformers", "7.8.9-rc1"))
        with patch.object(v, "_curated_product_repos", return_value={}):
            self.assertIsNone(v._curated_release(signal("", "LangGraph v7.8.9")))

    def test_curated_names_need_an_unambiguous_version(self):
        for title in ("LangGraph is popular", "WidgetGraph v7.8.9", "LangGraph and Chroma 7.8.9",
                      "LangGraph 7.8.9 or 7.9.0", "LangGraph >=7.8.9"):
            self.assertIsNone(v._curated_release(signal("", title)), title)
        s = signal("", "WidgetGraph performance report")
        s.summary = "Compared against LangGraph 7.8.9."
        self.assertIsNone(v._curated_release(s))
        explicit = signal("https://github.com/other/langgraph/releases/tag/v7.8.9", "LangGraph 7.8.9")
        self.assertIsNone(v._curated_release(explicit))

    def test_curated_release_path_never_searches_and_distinguishes_missing_error(self):
        s = signal("", "LangGraph 7.8.9")
        c = TrendCluster(s.title, [s])
        repo = "langchain-ai/langgraph"
        for reply, confidence, verified, missing in (
            ({"repo": repo, "matched_release": {"tag": "v7.8.9"}}, .75, True, False),
            ({"repo": repo, "release_found": False}, .20, False, True),
            ({"error": "HTTP 403"}, .40, False, False),
            ({"repo": repo, "matched_release": {"tag": "v7.9.0"}}, .40, False, False),
        ):
            calls = []
            def dispatch(name, args):
                calls.append((name, args))
                return reply
            facts = v.VerificationAgent(tool_runner=dispatch)._deterministic_loop(c)
            self.assertEqual(calls, [("verify_release", {"repo": repo, "version": "7.8.9"})])
            self.assertEqual(v._score(c, facts), confidence)
            self.assertEqual(facts.claim_verified, verified)
            self.assertEqual(facts.release_missing, missing)

    def test_curated_release_is_checked_even_if_model_stops_immediately(self):
        class StoppingClient:
            def __init__(self):
                self.chat = self.completions = self
            def create(self, **kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))])
        s = signal("", "LangGraph 7.8.9")
        calls = []
        def dispatch(name, args):
            calls.append(name)
            return {"matched_release": {"tag": "v7.8.9"}}
        result = v.VerificationAgent(client=StoppingClient(), tool_runner=dispatch).run(TrendCluster(s.title, [s]))
        self.assertEqual(calls, ["verify_release"])
        self.assertTrue(result.claim_verified)
        self.assertEqual(result.verified_source_count, 1)
        self.assertEqual(result.confidence, .75)

    def test_bare_name_dispatch_cannot_use_open_search(self):
        with patch.object(v.tools, "call_tool", side_effect=AssertionError("open search called")):
            self.assertIn("error", v._verification_tool("github_lookup", {"query": "LangGraph"}))

    def test_independent_reports_count_but_mirrors_and_same_host_do_not(self):
        a = signal("https://news.example.org/article")
        b = signal("https://engineering.example.net/article")
        first = {"url": a.url, "text": a.title + ". Technical explanation."}
        second = {"url": b.url, "text": b.title + ". Independently reproduced."}
        self.assertEqual(source_facts([a, b], {a.url: first, b.url: second}).verified_source_count, 2)
        self.assertEqual(source_facts([a, b], {a.url: first, b.url: {**first, "url": b.url}}).verified_source_count, 1)
        b.url = "https://news.example.org/other"
        self.assertEqual(source_facts([a, b], {a.url: first, b.url: {**second, "url": b.url}}).verified_source_count, 1)

    def test_official_document_is_primary_even_if_signal_is_secondary(self):
        s = signal("https://openai.com/index/synthetic-regression-example")
        facts = source_facts([s], {s.url: {"url": s.url, "text": s.title}})
        self.assertTrue(facts.primary_supported)
        self.assertEqual(facts.verified_source_count, 1)

    def test_outage_or_unrelated_page_never_corroborates(self):
        s = signal("https://news.example.org/article", tier="primary")
        for doc in ({"error": "HTTP 403"}, {"missing": True},
                    {"text": "WidgetGraph pricing and support"}):
            self.assertEqual(source_facts([s], {s.url: doc}).verified_source_count, 0)

    def test_supported_conflicting_versions_need_clarification(self):
        a = signal("https://news.example.org/a", "WidgetGraph 1.0 adds durable workflow checkpoints")
        b = signal("https://other.example.org/b", "WidgetGraph 2.0 adds durable workflow checkpoints")
        facts = source_facts([a, b], {a.url: {"url": a.url, "text": a.title}, b.url: {"url": b.url, "text": b.title}})
        self.assertTrue(facts.source_conflict)
        self.assertLess(v._score(TrendCluster(a.title, [a, b]), facts), .5)

    def test_secondary_bare_name_cannot_verify_through_release_call(self):
        s = signal("https://news.example.org/article", "WidgetGraph v1.2.3")
        acc = v._Accumulator(TrendCluster(s.title, [s]))
        acc.record("github_lookup", {"query": "widgetgraph"},
                   {"results": [{"full_name": "unrelated/widgetgraph"}]}, "lookup")
        acc.record("verify_release", {"repo": "unrelated/widgetgraph", "version": "v1.2.3"},
                   {"matched_release": {"tag": "v1.2.3"}}, "check")
        self.assertFalse(acc.facts().repo_exists)
        self.assertFalse(acc.facts().claim_verified)

    def test_missing_release_and_outage_are_distinct_from_first_party_prior(self):
        s = signal("https://github.com/example/widgetgraph/releases/tag/v1.2.3", "WidgetGraph v1.2.3", "primary")
        cluster = TrendCluster(s.title, [s])
        args = {"repo": "example/widgetgraph", "version": "v1.2.3"}
        for result, expected in (({"repo": args["repo"], "release_found": False}, .2),
                                 ({"error": "offline"}, .4)):
            acc = v._Accumulator(cluster)
            acc.record("verify_release", args, result, "check")
            self.assertEqual(v._score(cluster, acc.facts()), expected)
            self.assertFalse(acc.facts().claim_verified)
        prose = signal("https://publisher.example.org/announcement", tier="primary")
        self.assertEqual(v._score(TrendCluster(prose.title, [prose]), v.Facts([], [], 0, False, False, False)), .6)

    def test_confirmed_sibling_cannot_verify_an_unchecked_release(self):
        first = signal("https://github.com/example/widgetgraph/releases/tag/v1.2.3", "WidgetGraph v1.2.3")
        second = signal("https://github.com/example/widgetgraph/releases/tag/v9.0.0", "WidgetGraph v9.0.0")
        cluster = TrendCluster(first.title, [first, second])
        acc = v._Accumulator(cluster)
        acc.record("verify_release", {"repo": "example/widgetgraph", "version": "v1.2.3"},
                   {"matched_release": {"tag": "v1.2.3"}}, "check")
        self.assertFalse(acc.facts().claim_verified)
        self.assertTrue(acc.facts().release_unchecked)
        self.assertFalse(acc.facts().release_missing)
        self.assertLess(v._score(cluster, acc.facts()), .5)

    def test_decoded_tag_requires_exact_matching_release(self):
        s = signal("https://github.com/example/widgetgraph/releases/tag/widget%3D%3D1.2.3", "WidgetGraph release")
        self.assertEqual(v._claim_tag(s), "widget==1.2.3")
        cluster = TrendCluster(s.title, [s])
        args = {"repo": "example/widgetgraph", "version": "widget==1.2.3"}
        for tag, valid in (("widget==1.2.3", True), ("1.2.3", False), ("widget==9.0.0", False)):
            acc = v._Accumulator(cluster)
            acc.record("verify_release", args, {"matched_release": {"tag": tag}}, "check")
            self.assertEqual(acc.facts().claim_verified, valid)

    def test_repository_redirect_establishes_identity_for_release(self):
        redirect = SimpleNamespace(is_redirect=True, headers={"Location": "https://api.github.com/repositories/123"})
        response = SimpleNamespace(is_redirect=False, status_code=200, ok=True,
                                   json=lambda: {"full_name": "new-owner/widgetgraph", "html_url": "https://github.com/new-owner/widgetgraph"})
        with patch.object(v.tools, "_with_cache", side_effect=lambda name, args, compute: compute()), \
                patch.object(v.tools.requests, "get", side_effect=[redirect, response]):
            result = v._lookup_exact_repository("old-owner/widgetgraph")
        self.assertIsNotNone(v._match_result("old-owner/widgetgraph", result))
        s = signal("https://github.com/old-owner/widgetgraph/releases/tag/v1.2.3", "WidgetGraph v1.2.3")
        acc = v._Accumulator(TrendCluster(s.title, [s]))
        acc.record("github_lookup", {"query": "old-owner/widgetgraph"}, result, "lookup")
        acc.record("verify_release", {"repo": "new-owner/widgetgraph", "version": "v1.2.3"},
                   {"matched_release": {"tag": "v1.2.3"}}, "check")
        self.assertTrue(acc.facts().claim_verified)
        self.assertFalse(acc.facts().repo_missing)

    def test_search_similarity_does_not_establish_redirect(self):
        result = {"results": [{"full_name": "other/widgetgraph", "redirected_from": "old/widgetgraph"}]}
        self.assertIsNone(v._match_result("old/widgetgraph", result))


if __name__ == "__main__":
    unittest.main()
