import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from dots_workflow import evidence, content
from dots_workflow.cli import render_html

ROOT = Path(__file__).resolve().parents[1]


def codes(result, severity=None):
    return {x["code"] for x in result["issues"] if severity is None or x["severity"] == severity}


class EvidenceTests(unittest.TestCase):
    def test_all_eight_research_fixtures(self):
        cases = json.loads((ROOT / "fixtures/evidence-brief.json").read_text())["cases"]
        self.assertEqual(len(cases), 8)
        for case in cases:
            with self.subTest(case=case["id"]):
                with patch("socket.socket", side_effect=AssertionError("network prohibited")), patch("subprocess.run", side_effect=AssertionError("subprocess prohibited")):
                    result = evidence.run(case["input"])
                expected = case["expected"]
                self.assertTrue(set(expected.get("errors", [])) <= codes(result, "error"))
                self.assertTrue(set(expected.get("warnings", [])) <= codes(result, "warning"))
                self.assertEqual(result["external_actions"], [])
                self.assertTrue(result["untrusted_source_data"])
                self.assertTrue(all(not c["fact_certified"] for c in result["claims"]))
                if case["id"] == "E01":
                    self.assertEqual(codes(result, "error"), set())
                    self.assertEqual(result["claims"][0]["evidence_level"], "author_report")
                    self.assertEqual(result["sources"][0]["status"], "synthetic")
                if case["id"] == "E02":
                    self.assertIn("claims[0].source_ids[0]", [x.get("path") for x in result["issues"]])
                if case["id"] == "E03":
                    self.assertEqual(len(result["sources"]), 2)
                if case["id"] == "E06":
                    self.assertEqual(result["sources"][0]["text"], case["input"]["sources"][0]["text"])
                if case["id"] == "E07":
                    markup = render_html(result)
                    self.assertNotIn("<script>", markup)
                    self.assertNotIn('href="javascript:', markup)
                    self.assertIn("&lt;script&gt;", markup)
                if case["id"] == "E08":
                    self.assertEqual(result["claims"], [])

    def test_empty_input_requires_review(self):
        self.assertIn("no_claims", codes(evidence.run({})))

    def test_orphan_source_is_found(self):
        result = evidence.run({"sources": [{"id": "unused", "text": "original", "status": "read"}]})
        self.assertIn("orphan_source", codes(result))

    def test_reproduction_requires_actual_record_fields(self):
        data = {"claims": [{"id": "C", "text": "Run", "evidence_level": "locally_reproduced", "test_id": "T"}], "tests": [{"id": "T", "status": "passed", "command": "python -m unittest", "observed": "12 tests passed"}]}
        result = evidence.run(data)
        self.assertNotIn("missing_reproduction_evidence", codes(result))
        self.assertFalse(result["claims"][0]["reproduction"]["executed_by_checker"])
        data["tests"][0]["status"] = "failed"
        self.assertIn("missing_reproduction_evidence", codes(evidence.run(data)))

    def test_duplicate_test_cannot_be_selected(self):
        test = {"id": "T", "status": "passed", "command": "x", "observed": "y"}
        result = evidence.run({"tests": [test, test], "claims": [{"id": "C", "text": "x", "evidence_level": "locally_reproduced", "test_id": "T"}]})
        self.assertIn("duplicate_test_id", codes(result))
        self.assertIn("missing_reproduction_evidence", codes(result))

    def test_malformed_collections_dont_crash(self):
        for value in (None, 4, "bad", {}):
            result = evidence.run({"sources": value, "claims": value})
            self.assertIn("invalid_collection", codes(result))
        result = evidence.run({"sources": [{"id": []}], "claims": [{"id": "C", "evidence_level": [], "source_ids": [None]}]})
        self.assertIn("invalid_evidence_level", codes(result))
        self.assertIn("invalid_reference_list", codes(result))

    def test_url_credentials_not_accepted(self):
        result = evidence.run({"sources": [{"id": "S", "url": "https://user:secret@example.invalid/x"}]})
        self.assertIn("invalid_url", codes(result))

    def test_long_unicode_text_roundtrip(self):
        text = "中文🪴" * 10000
        result = evidence.run({"sources": [{"id": "S", "text": text, "status": "synthetic"}]})
        self.assertEqual(result["sources"][0]["text"], text)

    def test_valid_permutation_is_semantically_stable(self):
        data = {"sources": [{"id": "S2", "status": "read", "text": "b"}, {"id": "S1", "status": "read", "text": "a"}], "claims": [{"id": "C2", "text": "b", "source_ids": ["S2"], "evidence_level": "author_report"}, {"id": "C1", "text": "a", "source_ids": ["S1"], "evidence_level": "official"}]}
        baseline = evidence.run(data)
        data["sources"].reverse()
        data["claims"].reverse()
        self.assertEqual(evidence.run(data), baseline)


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "examples/content.json").read_text())

    def test_example_preserves_review_and_sources(self):
        result = content.run(self.data)
        self.assertEqual(result["summary"]["error_count"], 0)
        self.assertIn("human_review_pending", codes(result))
        self.assertFalse(result["publication"]["authorization_to_publish"])
        self.assertFalse(result["publication"]["image_generated"])
        self.assertIsNone(result["metrics_summary"]["rates"]["clicks_per_impression"])
        self.assertIn("S1", content.publication_pack(result))

    def test_review_approval_does_not_publish(self):
        self.data["review"] = {"status": "approved", "reviewer": "合成审阅人"}
        result = content.run(self.data)
        self.assertNotIn("human_review_pending", codes(result))
        self.assertFalse(result["publication"]["authorization_to_publish"])
        self.assertEqual(result["external_actions"], [])

    def test_missing_and_zero_metrics_differ(self):
        self.data["metrics"] = {"impressions": 100, "clicks": 0, "saves": None}
        summary = content.run(self.data)["metrics_summary"]
        self.assertEqual(summary["rates"]["clicks_per_impression"], 0)
        self.assertIsNone(summary["rates"]["saves_per_impression"])
        self.data["metrics"] = {"impressions": 0, "clicks": 5}
        self.assertIn("metric_denominator_inconsistent", codes(content.run(self.data)))

    def test_invalid_metrics(self):
        for value in (-1, True, "30", float("inf"), 10**400):
            self.data["metrics"] = {"impressions": value}
            self.assertIn("invalid_metric", codes(content.run(self.data)))

    def test_unknown_draft_claim(self):
        self.data["draft"]["claim_ids"] = ["missing"]
        self.assertIn("unknown_claim_reference", codes(content.run(self.data)))

    def test_pack_fences_untrusted_text(self):
        self.data["draft"]["body"] = "<script>alert(1)</script>\n```\n![tracker](https://example.invalid/track)"
        pack = content.publication_pack(content.run(self.data))
        self.assertIn("````text\n<script>alert(1)</script>\n```\n![tracker](https://example.invalid/track)\n````", pack)
        self.assertIn("合成会议记录", pack)
        self.assertIn("审查记录", pack)


if __name__ == "__main__":
    unittest.main()
