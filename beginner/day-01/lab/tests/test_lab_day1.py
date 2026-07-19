from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB_ROOT))

import lab_day1  # noqa: E402


class Day1LabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = lab_day1.load_case()
        cls.outputs, cls.labels = lab_day1.load_cached_outputs()
        cls.report = lab_day1.analyze(cls.outputs, cls.case, cls.labels)

    def test_cached_fixture_contains_five_runs(self) -> None:
        self.assertEqual(len(self.outputs), 5)
        self.assertEqual(len(self.labels), 5)

    def test_prepared_expected_metrics(self) -> None:
        self.assertEqual(self.report["unique_output_rate"], 1.0)
        self.assertEqual(self.report["format_validity_rate"], 0.8)
        self.assertTrue(
            math.isclose(
                self.report["constraint_level_compliance"],
                0.675,
            )
        )
        self.assertEqual(self.report["all_constraints_pass_rate"], 0.4)
        self.assertEqual(self.report["semantic_pairwise_agreement"], 0.3)
        self.assertEqual(self.report["semantic_correctness_rate"], 0.6)

    def test_markdown_fenced_json_is_raw_format_failure(self) -> None:
        self.assertIsNone(lab_day1.parse_raw_json(self.outputs[2]))

    def test_valid_json_can_still_be_unsafe(self) -> None:
        checks = lab_day1.instruction_checks(self.outputs[3], self.case)
        self.assertIsNotNone(lab_day1.parse_raw_json(self.outputs[3]))
        self.assertFalse(checks["no_completed_action_claim"])
        self.assertFalse(checks["no_credential_delivery_claim"])

    def test_text_normalization_does_not_claim_semantic_equivalence(self) -> None:
        self.assertEqual(lab_day1.normalize(" A  B\n"), "a b")


if __name__ == "__main__":
    unittest.main()

