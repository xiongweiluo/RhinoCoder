"""Synthetic-only public commitment tests; no private holdout is opened."""
import json
import tempfile
import unittest
from pathlib import Path

from eval.test_c5_formal20_preparation import cases20
from tools.c5_formal20_owner_commitment import (
    FormalCommitmentError, _write_exclusive, build_public_commitment,
)
from training.c5_formal20_commitment import (
    FormalCommitmentValidationError, validate_public_commitment,
)
from tools.c5_formal20_public_preflight import preflight as public_preflight
from training.c5_holdout import sha256_file


def inputs():
    bindings = {
        "development_dataset_freeze_sha256": "1" * 64,
        "historical_exclusions_sha256": "2" * 64,
        "original80_public_commitment_file_sha256": "3" * 64,
        "original80_family_merkle_root_sha256": "4" * 64,
        "additional_exclusion_file_sha256": ["5" * 64],
    }
    encrypted = {"sha256": "6" * 64, "bytes": 1024, "format": "age-x25519"}
    attestation = {"actor": "repository_owner", "full_r_exclusion_inventory_reviewed": True,
        "semantic_near_duplicate_review_passed": True,
        "fixture_and_expected_geometry_reviewed": True,
        "encryption_roundtrip_verified": True,
        "keys_not_shared_with_development_agent": True,
        "sealed_at_utc": "2026-10-03T20:00:00Z"}
    preflight = {"status": "owner_private_automated_exclusion_preflight_only_not_formal_freeze",
                 "candidate_count": 20, "development_count": 440, "original80_count": 80,
                 "original80_public_merkle_identity_verified": True,
                 "exact_numeric_or_092_near_duplicate_overlap_count": 0}
    return bindings, encrypted, attestation, preflight


class Formal20OwnerCommitmentTests(unittest.TestCase):
    def _validate(self, value, bindings):
        return validate_public_commitment(value,
            expected_development_freeze_sha256=bindings["development_dataset_freeze_sha256"],
            expected_historical_exclusions_sha256=bindings["historical_exclusions_sha256"],
            expected_original80_commitment_file_sha256=bindings["original80_public_commitment_file_sha256"],
            expected_original80_merkle_root_sha256=bindings["original80_family_merkle_root_sha256"])

    def test_public_commitment_contains_no_private_task_or_execution_grant(self):
        bindings, encrypted, attestation, preflight = inputs()
        value = build_public_commitment(cases20(), bindings=bindings,
                                        encrypted=encrypted, attestation=attestation,
                                        preflight_report=preflight)
        raw = json.dumps(value, ensure_ascii=False)
        self.assertEqual((value["family_count"], value["route_slots"]), (20, 40))
        self.assertFalse(value["execution_ready"])
        self.assertNotIn("Synthetic only", raw)
        self.assertNotIn("expected_operations", raw)
        self.assertEqual(value["exclusions"]["additional_exclusion_file_sha256"], bindings["additional_exclusion_file_sha256"])
        self.assertEqual(value["exclusions"]["automated_exact_numeric_or_092_near_duplicate_overlap_count"], 0)
        checked = self._validate(value, bindings)
        self.assertFalse(checked["execution_ready"])
        self.assertEqual(checked["private_task_rows_read"], 0)

    def test_public_validator_rejects_text_or_replacement_hash(self):
        bindings, encrypted, attestation, preflight = inputs()
        value = build_public_commitment(cases20(), bindings=bindings,
                                        encrypted=encrypted, attestation=attestation,
                                        preflight_report=preflight)
        value["task_text"] = "private text must never be public"
        with self.assertRaises(FormalCommitmentValidationError): self._validate(value, bindings)
        value.pop("task_text")
        value["exclusions"]["original80_family_merkle_root_sha256"] = "f" * 64
        with self.assertRaises(FormalCommitmentValidationError): self._validate(value, bindings)

    def test_missing_owner_semantic_review_rejected(self):
        bindings, encrypted, attestation, preflight = inputs()
        attestation["semantic_near_duplicate_review_passed"] = False
        with self.assertRaisesRegex(FormalCommitmentError, "attestation_incomplete"):
            build_public_commitment(cases20(), bindings=bindings,
                                    encrypted=encrypted, attestation=attestation,
                                    preflight_report=preflight)

    def test_duplicate_public_output_cannot_overwrite(self):
        bindings, encrypted, attestation, preflight = inputs()
        value = build_public_commitment(cases20(), bindings=bindings,
                                        encrypted=encrypted, attestation=attestation,
                                        preflight_report=preflight)
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp).resolve() / "owner-private"; private.mkdir(mode=0o700)
            path = private / "commitment.json"
            _write_exclusive(path, value)
            with self.assertRaises(FileExistsError):
                _write_exclusive(path, value)
            self.assertEqual(json.loads(path.read_text()), value)

    def test_public_cli_preflight_reads_only_synthetic_public_json(self):
        root = Path(__file__).resolve().parents[1]
        bindings, encrypted, attestation, owner_preflight = inputs()
        bindings["development_dataset_freeze_sha256"] = sha256_file(root / "eval/c5/dataset-v2-freeze-manifest.json")
        bindings["historical_exclusions_sha256"] = sha256_file(root / "eval/c5/historical-exclusions.json")
        bindings["original80_public_commitment_file_sha256"] = sha256_file(root / "eval/c5/final-holdout-commitment.json")
        bindings["original80_family_merkle_root_sha256"] = json.loads(
            (root / "eval/c5/final-holdout-commitment.json").read_text())["fingerprints"]["family_merkle_root_sha256"]
        value = build_public_commitment(cases20(), bindings=bindings,
                                        encrypted=encrypted, attestation=attestation,
                                        preflight_report=owner_preflight)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "synthetic-public.json"
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            checked = public_preflight(path)
        self.assertEqual(checked["private_task_rows_read"], 0)
        self.assertFalse(checked["execution_ready"])


if __name__ == "__main__": unittest.main()
