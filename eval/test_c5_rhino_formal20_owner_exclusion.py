"""Synthetic-only tests; no original holdout or proposed formal tasks are read."""
import hashlib
import unittest

from training.c5_contract import CORE_INVOCATION_TOOLS
from tools.c5_rhino_formal20_owner_exclusion import (
    ExclusionPreflightError, _merkle_root, _require_owner_private_path, audit_candidates,
)


def _distinct(prefix, index):
    digest = hashlib.sha256((prefix + str(index)).encode()).hexdigest()
    return prefix + "-" + digest.translate(str.maketrans("0123456789", "ghijklmnop"))


class Formal20OwnerExclusionTests(unittest.TestCase):
    def setUp(self):
        strata = (["core_tool"] * 12 + ["multistep"] * 2 +
                  ["clarification"] * 2 + ["refusal"] * 2 + ["error_recovery"] * 2)
        self.candidates = [
            {"family_id": f"new-family-{index:02d}", "template_family": f"new-template-{index:02d}",
             "stratum": stratum, "primary_tool": CORE_INVOCATION_TOOLS[index] if index < 12 else None,
             "task_text": _distinct("candidate", index)}
            for index, stratum in enumerate(strata)
        ]
        self.development = [
            {"family_id": f"dev-family-{index:03d}",
             "records": [{"user_step": _distinct("development", index)}]}
            for index in range(440)
        ]
        self.original80 = [
            {"family_id": f"original-family-{index:02d}",
             "records": [{"user_step": _distinct("original", index)}]}
            for index in range(80)
        ]
        self.extra = [{"family_id": "prior-development-probe", "task_text": _distinct("extra", 0)}]

    def audit(self):
        return audit_candidates(self.candidates, self.development, self.original80, self.extra,
                                original_root=_merkle_root(self.original80), historical_numeric_hashes=set())

    def test_clean_synthetic_inputs_are_still_not_formal_freeze(self):
        result = self.audit()
        self.assertEqual(result["candidate_count"], 20)
        self.assertTrue(result["manual_semantic_and_complete_r_exclusion_review_still_required"])
        self.assertFalse(result["formal_commitment_ready"])
        self.assertFalse(result["formal_run_authorized"])

    def test_frozen_development_template_overlap_fails(self):
        self.candidates[0]["task_text"] = self.development[0]["records"][0]["user_step"]
        with self.assertRaisesRegex(ExclusionPreflightError, "numeric_template_overlap"):
            self.audit()

    def test_original80_template_overlap_fails(self):
        self.candidates[0]["task_text"] = self.original80[0]["records"][0]["user_step"]
        with self.assertRaisesRegex(ExclusionPreflightError, "numeric_template_overlap"):
            self.audit()

    def test_development_probe_overlap_fails(self):
        self.candidates[0]["task_text"] = self.extra[0]["task_text"]
        with self.assertRaisesRegex(ExclusionPreflightError, "numeric_template_overlap"):
            self.audit()

    def test_candidate_family_reuse_fails(self):
        self.candidates[1]["template_family"] = self.candidates[0]["template_family"]
        with self.assertRaisesRegex(ExclusionPreflightError, "candidate_family_or_template_reuse"):
            self.audit()

    def test_original80_identity_mismatch_fails(self):
        with self.assertRaisesRegex(ExclusionPreflightError, "original80_identity_mismatch"):
            audit_candidates(self.candidates, self.development, self.original80, self.extra,
                             original_root="0" * 64, historical_numeric_hashes=set())

    def test_later_user_step_overlap_fails(self):
        self.original80[0]['records'].append({'user_step': self.candidates[0]['task_text']})
        with self.assertRaisesRegex(ExclusionPreflightError, 'numeric_template_overlap'):
            self.audit()

    def test_historical_template_family_overlap_fails(self):
        self.extra[0]['template_family'] = self.candidates[0]['template_family']
        with self.assertRaisesRegex(ExclusionPreflightError, 'candidate_template_family_overlap'):
            self.audit()

    def test_missing_extra_exclusions_fail_closed(self):
        self.extra = []
        with self.assertRaisesRegex(ExclusionPreflightError, "incomplete_exclusion_population"):
            self.audit()

    def test_owner_private_body_inside_worktree_rejected(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(ExclusionPreflightError, "outside_all_worktrees"):
            _require_owner_private_path(root / "private-candidate.jsonl", [root])


if __name__ == "__main__":
    unittest.main()
