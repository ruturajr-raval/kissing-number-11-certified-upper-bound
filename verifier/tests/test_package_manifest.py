"""Adversarial tests for compact package-manifest bindings."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TEST_DIRECTORY = Path(__file__).resolve().parent
VERIFIER_DIRECTORY = TEST_DIRECTORY.parent
PROJECT_ROOT = VERIFIER_DIRECTORY.parent
SMOKE_WITNESS = TEST_DIRECTORY / "fixtures" / "smoke-exact-witness-v2.bin"
sys.path.insert(0, str(VERIFIER_DIRECTORY))

import package_manifest  # noqa: E402
from compact_certificate import canonical_block_layout  # noqa: E402
from compact_witness import MatrixBlock, WitnessReport  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackageManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.certificates = self.root / "certificates"
        self.certificates.mkdir()
        self.witness = (
            self.certificates / package_manifest.EXPECTED_WITNESS_FILENAME
        )
        shutil.copy2(SMOKE_WITNESS, self.witness)

        for token in (
            *package_manifest.EXPECTED_EVIDENCE_PATHS,
            *package_manifest.EXPECTED_SOURCE_PATHS,
        ):
            source = PROJECT_ROOT.joinpath(*Path(token).parts)
            destination = self.root.joinpath(*Path(token).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        self.evidence_hashes = {
            token: sha256(self.root.joinpath(*Path(token).parts))
            for token in package_manifest.EXPECTED_EVIDENCE_PATHS
        }
        self.source_hashes = {
            token: sha256(self.root.joinpath(*Path(token).parts))
            for token in package_manifest.EXPECTED_SOURCE_PATHS
        }
        self.descriptor = package_manifest._problem_descriptor_sha256(
            evidence_hashes=self.evidence_hashes,
            source_hashes=self.source_hashes,
        )
        self.source_fields = package_manifest._source_specification_fields(
            self.source_hashes
        )
        self.source_specification = package_manifest._specification_digest(
            self.source_fields
        )
        self.rounding_fields = (
            package_manifest._rounding_specification_fields(
                self.source_hashes,
                self.source_specification,
            )
        )
        self.rounding_specification = package_manifest._specification_digest(
            self.rounding_fields
        )
        self.verification_fields = (
            package_manifest._verification_specification_fields(
                self.source_hashes,
                self.source_specification,
                self.rounding_specification,
            )
        )
        self.verification_specification = (
            package_manifest._specification_digest(self.verification_fields)
        )
        self.witness_sha256 = sha256(self.witness)
        self.layout = canonical_block_layout(17)
        self.rank_sum = sum(block.dimension for block in self.layout)
        self.rational_count = sum(
            block.dimension * (block.dimension + 1) // 2
            for block in self.layout
        )
        self.fake_blocks = tuple(
            MatrixBlock(
                name=block.name,
                dimension=block.dimension,
                matrix=tuple(
                    tuple(
                        Fraction(int(row == column))
                        for column in range(block.dimension)
                    )
                    for row in range(block.dimension)
                ),
            )
            for block in self.layout
        )
        self.report = WitnessReport(
            sha256=self.witness_sha256,
            size_bytes=self.witness.stat().st_size,
            block_count=70,
            rank_sum=self.rank_sum,
            rational_count=self.rational_count,
            maximum_numerator_bits=1,
            maximum_denominator_bits=1,
        )
        self.document = self._document()
        self.manifest = (
            self.certificates / "kn11-degree17-certificate-v2.json"
        )
        self._write_document()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _document(self) -> dict[str, object]:
        return {
            "affiliation": package_manifest.EXPECTED_AFFILIATION,
            "author": package_manifest.EXPECTED_AUTHOR,
            "blocks": [
                {
                    "dimension": block.dimension,
                    "name": block.name,
                    "rank": block.dimension,
                }
                for block in self.layout
            ],
            "evidence": [
                {"path": token, "sha256": self.evidence_hashes[token]}
                for token in package_manifest.EXPECTED_EVIDENCE_PATHS
            ],
            "format": package_manifest.EXPECTED_FORMAT,
            "format_version": package_manifest.EXPECTED_FORMAT_VERSION,
            "orcid": package_manifest.EXPECTED_ORCID,
            "problem": {
                "cos_theta": "1/2",
                "degree": 17,
                "dimension": 11,
                "fixed_objective": "86899/100",
                "formula_revision": (
                    package_manifest.EXPECTED_FORMULA_REVISION
                ),
                "problem_descriptor_sha256": self.descriptor,
                "sample_sha256": package_manifest.EXPECTED_SAMPLE_SHA256,
                "theorem": "tau_11 <= 868",
            },
            "provenance": {
                "rounding_specification": {
                    "digest": self.rounding_specification,
                    "fields": list(self.rounding_fields),
                },
                "source_specification": {
                    "digest": self.source_specification,
                    "fields": list(self.source_fields),
                },
                "verification_specification": {
                    "digest": self.verification_specification,
                    "fields": list(self.verification_fields),
                },
            },
            "sources": [
                {"path": token, "sha256": self.source_hashes[token]}
                for token in package_manifest.EXPECTED_SOURCE_PATHS
            ],
            "status": "candidate-exact-certificate",
            "verification": {
                "affine_identities_exact": True,
                "block_count": 70,
                "objective_exact": True,
                "positive_semidefinite_exact": True,
            },
            "witness": {
                "filename": package_manifest.EXPECTED_WITNESS_FILENAME,
                "maximum_denominator_bits": 1,
                "maximum_numerator_bits": 1,
                "rank_sum": self.rank_sum,
                "rational_count": self.rational_count,
                "sha256": self.witness_sha256,
                "size_bytes": self.witness.stat().st_size,
            },
        }

    def _write_document(self) -> None:
        self.manifest.write_text(
            json.dumps(
                self.document,
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="ascii",
        )

    def _fake_reader(self, data, layout, *, consumer, limits):
        self.assertEqual(data, self.witness.read_bytes())
        self.assertEqual(tuple(layout), self.layout)
        for block in self.fake_blocks:
            consumer(block)
        return self.report

    def _verify(self):
        with mock.patch.object(
            package_manifest,
            "read_compact_witness_bytes",
            side_effect=self._fake_reader,
        ):
            return package_manifest.verify_manifest_bindings(
                self.manifest,
                project_root=self.root,
            )

    def test_valid_manifest_binds_every_required_file(self) -> None:
        isolated_help = subprocess.run(
            [
                sys.executable,
                "-I",
                "-E",
                "-s",
                str(VERIFIER_DIRECTORY / "verify_compact_package.py"),
                "--help",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertIn("Verify the complete dimension-11", isolated_help.stdout)
        report = self._verify()
        self.assertEqual(report.problem_descriptor_sha256, self.descriptor)
        self.assertEqual(
            report.source_count,
            len(package_manifest.EXPECTED_SOURCE_PATHS),
        )
        self.assertEqual(
            report.evidence_count,
            len(package_manifest.EXPECTED_EVIDENCE_PATHS),
        )
        self.assertEqual(
            report.verification_specification,
            self.verification_specification,
        )

    def test_rejects_non_full_rank_manifest_metadata(self) -> None:
        self.document["blocks"][0]["rank"] -= 1
        self._write_document()
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "rank must equal its dimension",
        ):
            self._verify()

    def test_complete_package_parses_witness_once(self) -> None:
        replay = mock.Mock()
        replay.consume = mock.Mock()
        replay.finish.return_value = SimpleNamespace(
            witness=self.report,
            positive_definite_block_count=70,
            exact_psd_fallback_block_count=0,
        )
        reads = 0

        def read_once(data, layout, *, consumer, limits):
            nonlocal reads
            reads += 1
            return self._fake_reader(
                data,
                layout,
                consumer=consumer,
                limits=limits,
            )

        with (
            mock.patch.object(
                package_manifest,
                "CompactCertificateReplay",
                return_value=replay,
            ),
            mock.patch.object(
                package_manifest,
                "read_compact_witness_bytes",
                side_effect=read_once,
            ),
        ):
            report = package_manifest.verify_compact_package(
                self.manifest,
                project_root=self.root,
            )

        self.assertEqual(reads, 1)
        replay.finish.assert_called_once_with(self.report)
        self.assertIs(report.certificate, replay.finish.return_value)

    def test_complete_package_requires_strict_interval_positivity(self) -> None:
        replay = mock.Mock()
        replay.consume = mock.Mock()
        replay.finish.return_value = SimpleNamespace(
            witness=self.report,
            positive_definite_block_count=69,
            exact_psd_fallback_block_count=1,
        )
        with (
            mock.patch.object(
                package_manifest,
                "CompactCertificateReplay",
                return_value=replay,
            ),
            mock.patch.object(
                package_manifest,
                "read_compact_witness_bytes",
                side_effect=self._fake_reader,
            ),
            self.assertRaisesRegex(
                package_manifest.PackageManifestError,
                "strict interval positivity",
            ),
        ):
            package_manifest.verify_compact_package(
                self.manifest,
                project_root=self.root,
            )

    def test_bound_source_tamper_is_rejected(self) -> None:
        path = self.root / "docs" / "THEOREM_BRIDGE.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "SHA-256 mismatch",
        ):
            self._verify()

    def test_problem_descriptor_tamper_is_rejected(self) -> None:
        self.document["problem"]["problem_descriptor_sha256"] = "f" * 64
        self._write_document()
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "problem descriptor",
        ):
            self._verify()

    def test_unsafe_bound_path_is_rejected(self) -> None:
        self.document["sources"][0]["path"] = "../Manifest.toml"
        self._write_document()
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "unsafe path",
        ):
            self._verify()

    def test_duplicate_json_key_is_rejected(self) -> None:
        text = self.manifest.read_text(encoding="ascii")
        self.manifest.write_text(
            text.replace("{", '{"author":"duplicate",', 1),
            encoding="ascii",
        )
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "duplicate JSON key",
        ):
            self._verify()

    def test_published_manifest_hash_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "published value",
        ):
            with mock.patch.object(
                package_manifest,
                "read_compact_witness_bytes",
                side_effect=self._fake_reader,
            ):
                package_manifest.verify_manifest_bindings(
                    self.manifest,
                    project_root=self.root,
                    expected_manifest_sha256="0" * 64,
                )

    def test_published_verification_specification_mismatch_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "published value",
        ):
            with mock.patch.object(
                package_manifest,
                "read_compact_witness_bytes",
                side_effect=self._fake_reader,
            ):
                package_manifest.verify_manifest_bindings(
                    self.manifest,
                    project_root=self.root,
                    expected_verification_specification="0" * 64,
                )

    def test_source_provenance_field_tamper_is_rejected(self) -> None:
        fields = self.document["provenance"]["source_specification"]["fields"]
        fields[1] = "mode=optimization"
        self.document["provenance"]["source_specification"]["digest"] = (
            package_manifest._specification_digest(fields)
        )
        self._write_document()
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "fields are inconsistent",
        ):
            self._verify()

    def test_rounding_provenance_digest_tamper_is_rejected(self) -> None:
        self.document["provenance"]["rounding_specification"]["digest"] = (
            "f" * 64
        )
        self._write_document()
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "digest is inconsistent",
        ):
            self._verify()

    def test_verification_provenance_field_tamper_is_rejected(self) -> None:
        fields = self.document["provenance"]["verification_specification"][
            "fields"
        ]
        fields[-1] = "verification_mode=unbound"
        self.document["provenance"]["verification_specification"]["digest"] = (
            package_manifest._specification_digest(fields)
        )
        self._write_document()
        with self.assertRaisesRegex(
            package_manifest.PackageManifestError,
            "fields are inconsistent",
        ):
            self._verify()


if __name__ == "__main__":
    unittest.main()
