from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "build_release_assets.py"
SPEC = importlib.util.spec_from_file_location("build_release_assets", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load release asset module")
release_assets = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_assets
SPEC.loader.exec_module(release_assets)


class ReleaseAssetTests(unittest.TestCase):
    def test_asset_names_include_all_release_objects(self) -> None:
        self.assertEqual(
            release_assets.asset_names("1.2.3"),
            {
                "certificate": (
                    "kissing-number-11-certified-upper-bound-"
                    "certificate-v1.2.3.tar.gz"
                ),
                "paper": (
                    "kissing-number-11-certified-upper-bound-"
                    "paper-v1.2.3.pdf"
                ),
                "source": (
                    "kissing-number-11-certified-upper-bound-"
                    "source-v1.2.3.tar.gz"
                ),
            },
        )

    def test_project_version_matches_candidate_metadata(self) -> None:
        self.assertEqual(release_assets.project_version("HEAD"), "0.1.0")

    def test_checksum_writer_is_sorted_and_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            (directory / "z.bin").write_bytes(b"z")
            (directory / "a.bin").write_bytes(b"a")
            release_assets.write_checksums(
                directory,
                {"second": "z.bin", "first": "a.bin"},
            )
            self.assertEqual(
                (directory / "SHA256SUMS").read_text(
                    encoding="ascii"
                ).splitlines(),
                [
                    f"{hashlib.sha256(b'a').hexdigest()}  a.bin",
                    f"{hashlib.sha256(b'z').hexdigest()}  z.bin",
                ],
            )

    def test_checksum_parser_rejects_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            path = Path(directory_text) / "SHA256SUMS"
            path.write_text(
                f"{'0' * 64}  asset\n{'0' * 64}  asset\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                release_assets.read_checksums(path)

    def test_source_archive_is_deterministic_and_ref_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            first = directory / "first.tar.gz"
            second = directory / "second.tar.gz"
            version = release_assets.project_version("HEAD")
            release_assets.build_source_archive(first, version, "HEAD")
            release_assets.build_source_archive(second, version, "HEAD")
            self.assertEqual(
                release_assets.sha256(first),
                release_assets.sha256(second),
            )
            release_assets.verify_source_archive(first, version, "HEAD")

    def test_certificate_archive_is_deterministic_and_standalone(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            first = directory / "first.tar.gz"
            second = directory / "second.tar.gz"
            version = release_assets.project_version("HEAD")
            release_assets.build_certificate_archive(first, version, "HEAD")
            release_assets.build_certificate_archive(second, version, "HEAD")
            self.assertEqual(
                release_assets.sha256(first),
                release_assets.sha256(second),
            )
            release_assets.verify_certificate_archive(first, version, "HEAD")
            paths = set(release_assets.certificate_file_paths("HEAD"))
            self.assertIn(
                "certificates/kn11-degree17-certificate-v2.json",
                paths,
            )
            self.assertIn(
                "certificates/kn11-degree17-witness-v2.bin",
                paths,
            )
            self.assertIn("verifier/verify_compact_package.py", paths)
            self.assertIn("docs/THEOREM_BRIDGE.md", paths)

    def test_source_archive_rejects_duplicate_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            path = Path(directory_text) / "duplicate.tar.gz"
            entry = release_assets.TreeEntry("payload", 0o644, "payload")
            prefix = "example-v0.1.0"
            with tarfile.open(path, mode="w:gz") as archive:
                for _ in range(2):
                    info = tarfile.TarInfo(f"{prefix}/payload")
                    info.size = 1
                    archive.addfile(info, io.BytesIO(b"x"))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                release_assets.verify_archive(path, prefix, [entry])

    def test_tag_name_must_match_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            release_assets.validate_tag("HEAD", "v9.9.9", "0.1.0")

    def test_correct_tag_name_must_point_to_selected_commit(self) -> None:
        with mock.patch.object(
            release_assets,
            "resolve_ref",
            side_effect=["a" * 40, "b" * 40],
        ):
            with self.assertRaisesRegex(ValueError, "expected"):
                release_assets.validate_tag("HEAD", "v0.1.0", "0.1.0")

    def test_remote_release_requires_exact_uploaded_asset_set(self) -> None:
        expected = {"one", "two"}
        payload = {
            "tagName": "v0.1.0",
            "isDraft": True,
            "isImmutable": False,
            "assets": [
                {
                    "name": name,
                    "state": "uploaded",
                    "digest": f"sha256:{'0' * 64}",
                    "size": 0,
                }
                for name in sorted(expected)
            ],
        }
        release_assets.validate_remote_release_payload(
            payload,
            "v0.1.0",
            expected,
            "draft",
        )
        payload["assets"].pop()
        with self.assertRaisesRegex(ValueError, "exact asset set"):
            release_assets.validate_remote_release_payload(
                payload,
                "v0.1.0",
                expected,
                "draft",
            )

    def test_remote_release_digests_match_local_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            path = directory / "asset"
            path.write_bytes(b"release asset")
            payload = {
                "tagName": "v0.1.0",
                "isDraft": False,
                "isImmutable": True,
                "assets": [
                    {
                        "name": path.name,
                        "state": "uploaded",
                        "digest": f"sha256:{release_assets.sha256(path)}",
                        "size": path.stat().st_size,
                    }
                ],
            }
            release_assets.validate_remote_release_payload(
                payload,
                "v0.1.0",
                {path.name},
                "published",
                directory,
                require_immutable=True,
            )
            payload["assets"][0]["digest"] = f"sha256:{'0' * 64}"
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                release_assets.validate_remote_release_payload(
                    payload,
                    "v0.1.0",
                    {path.name},
                    "published",
                    directory,
                    require_immutable=True,
                )


if __name__ == "__main__":
    unittest.main()
