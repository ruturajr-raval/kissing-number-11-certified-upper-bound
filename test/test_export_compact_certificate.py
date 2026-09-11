#!/usr/bin/env python3
"""Adversarial tests for descriptor-anchored compact-certificate export."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "export_compact_certificate.py"
SPEC = importlib.util.spec_from_file_location(
    "export_compact_certificate",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CompactCertificateExportTests(unittest.TestCase):
    def test_bound_read_rejects_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "root"
            outside = Path(name) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "payload.txt").write_text("outside\n", encoding="ascii")
            (root / "linked").symlink_to(outside, target_is_directory=True)
            descriptor = os.open(root, MODULE.directory_flags())
            try:
                with self.assertRaisesRegex(RuntimeError, "cannot open"):
                    MODULE.stable_bytes_at(
                        descriptor,
                        "linked/payload.txt",
                        1024,
                    )
            finally:
                os.close(descriptor)

    def test_snapshot_copy_is_read_only_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "root"
            snapshot = Path(name) / "snapshot"
            root.mkdir()
            snapshot.mkdir()
            payload = b"bound source bytes\n"
            (root / "source.txt").write_bytes(payload)
            root_descriptor = os.open(root, MODULE.directory_flags())
            snapshot_descriptor = os.open(snapshot, MODULE.directory_flags())
            try:
                with (
                    mock.patch.object(MODULE, "SOURCE_PATHS", ("source.txt",)),
                    mock.patch.object(MODULE, "EVIDENCE_PATHS", ()),
                ):
                    hashes = MODULE.copy_bound_files(
                        root_descriptor,
                        snapshot_descriptor,
                    )
            finally:
                os.close(snapshot_descriptor)
                os.close(root_descriptor)
            copied = snapshot / "source.txt"
            self.assertEqual(copied.read_bytes(), payload)
            self.assertEqual(
                hashes["source.txt"],
                hashlib.sha256(payload).hexdigest(),
            )
            self.assertEqual(stat.S_IMODE(copied.stat().st_mode) & 0o222, 0)

    def test_publication_replaces_symlink_without_following_target(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "root"
            snapshot = Path(name) / "snapshot"
            certificates = root / "certificates"
            generated = snapshot / "certificates"
            root.mkdir()
            certificates.mkdir()
            generated.mkdir(parents=True)
            outside = Path(name) / "outside.txt"
            outside.write_bytes(b"do not modify\n")
            witness = b"fixed witness bytes"
            manifest = (
                json.dumps(
                    {
                        "witness": {
                            "filename": MODULE.WITNESS_FILENAME,
                            "sha256": hashlib.sha256(witness).hexdigest(),
                            "size_bytes": len(witness),
                        }
                    },
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            (generated / MODULE.WITNESS_FILENAME).write_bytes(witness)
            (generated / MODULE.MANIFEST_FILENAME).write_bytes(manifest)
            (certificates / MODULE.WITNESS_FILENAME).symlink_to(outside)

            root_descriptor = os.open(root, MODULE.directory_flags())
            snapshot_descriptor = os.open(snapshot, MODULE.directory_flags())
            try:
                captured_witness, captured_manifest = (
                    MODULE.capture_generated_pair(snapshot_descriptor)
                )
                (generated / MODULE.WITNESS_FILENAME).write_bytes(
                    b"replaced after capture"
                )
                MODULE.publish_outputs(
                    root_descriptor,
                    captured_witness,
                    captured_manifest,
                )
            finally:
                os.close(snapshot_descriptor)
                os.close(root_descriptor)

            published_witness = certificates / MODULE.WITNESS_FILENAME
            self.assertFalse(published_witness.is_symlink())
            self.assertEqual(published_witness.read_bytes(), witness)
            self.assertEqual(
                (certificates / MODULE.MANIFEST_FILENAME).read_bytes(),
                manifest,
            )
            self.assertEqual(outside.read_bytes(), b"do not modify\n")

    def test_copy_exact_input_returns_digest(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "root"
            snapshot = Path(name) / "snapshot"
            (root / "build").mkdir(parents=True)
            snapshot.mkdir()
            payload = b"serialized exact input\n"
            (root / MODULE.EXACT_INPUT_PATH).write_bytes(payload)
            root_descriptor = os.open(root, MODULE.directory_flags())
            snapshot_descriptor = os.open(snapshot, MODULE.directory_flags())
            try:
                digest = MODULE.copy_exact_input(
                    root_descriptor,
                    snapshot_descriptor,
                )
            finally:
                os.close(snapshot_descriptor)
                os.close(root_descriptor)
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
            self.assertEqual(
                (snapshot / MODULE.EXACT_INPUT_PATH).read_bytes(),
                payload,
            )

    def test_manifest_install_failure_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            certificates = root / "certificates"
            certificates.mkdir()
            old_witness = b"old witness"
            old_manifest = (
                json.dumps(
                    {
                        "witness": {
                            "filename": MODULE.WITNESS_FILENAME,
                            "sha256": hashlib.sha256(old_witness).hexdigest(),
                            "size_bytes": len(old_witness),
                        }
                    },
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            new_witness = b"new witness with different bytes"
            new_manifest = (
                json.dumps(
                    {
                        "witness": {
                            "filename": MODULE.WITNESS_FILENAME,
                            "sha256": hashlib.sha256(new_witness).hexdigest(),
                            "size_bytes": len(new_witness),
                        }
                    },
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            (certificates / MODULE.WITNESS_FILENAME).write_bytes(old_witness)
            (certificates / MODULE.MANIFEST_FILENAME).write_bytes(old_manifest)
            root_descriptor = os.open(root, MODULE.directory_flags())
            replace = os.replace
            replacements = 0

            def fail_manifest_install(*args, **kwargs):
                nonlocal replacements
                replacements += 1
                if replacements == 2:
                    raise OSError("injected manifest install failure")
                return replace(*args, **kwargs)

            try:
                with mock.patch.object(
                    MODULE.os,
                    "replace",
                    side_effect=fail_manifest_install,
                ):
                    with self.assertRaisesRegex(
                        OSError,
                        "manifest install failure",
                    ):
                        MODULE.publish_outputs(
                            root_descriptor,
                            new_witness,
                            new_manifest,
                        )
            finally:
                os.close(root_descriptor)

            self.assertEqual(
                (certificates / MODULE.WITNESS_FILENAME).read_bytes(),
                new_witness,
            )
            self.assertEqual(
                (certificates / MODULE.MANIFEST_FILENAME).read_bytes(),
                old_manifest,
            )
            with self.assertRaisesRegex(RuntimeError, "wrong witness"):
                MODULE.validate_generated_pair(new_witness, old_manifest)

    def test_export_path_bindings_match_independent_verifier(self) -> None:
        source = (
            ROOT / "verifier" / "package_manifest.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        bindings: dict[str, tuple[str, ...]] = {}
        expected_names = {
            "EXPECTED_SOURCE_PATHS",
            "EXPECTED_EVIDENCE_PATHS",
        }
        for statement in tree.body:
            if not isinstance(statement, ast.Assign):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id in expected_names:
                    value = ast.literal_eval(statement.value)
                    self.assertIsInstance(value, tuple)
                    bindings[target.id] = value

        self.assertEqual(
            MODULE.SOURCE_PATHS,
            bindings["EXPECTED_SOURCE_PATHS"],
        )
        self.assertEqual(
            MODULE.EVIDENCE_PATHS,
            bindings["EXPECTED_EVIDENCE_PATHS"],
        )

    def test_failed_output_stage_removes_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            descriptor = os.open(root, MODULE.directory_flags())
            try:
                with mock.patch.object(
                    MODULE.os,
                    "fsync",
                    side_effect=OSError("injected failure"),
                ):
                    with self.assertRaisesRegex(OSError, "injected failure"):
                        MODULE.stage_output(
                            descriptor,
                            MODULE.WITNESS_FILENAME,
                            b"partial",
                        )
                self.assertEqual(os.listdir(descriptor), [])
            finally:
                os.close(descriptor)

    def test_snapshot_cleanup_does_not_delete_replacement_directory(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            root.mkdir(exist_ok=True)
            with mock.patch.object(MODULE, "ROOT", root):
                with MODULE.private_snapshot() as (
                    root_descriptor,
                    snapshot_descriptor,
                ):
                    build = os.open(
                        "build",
                        MODULE.directory_flags(),
                        dir_fd=root_descriptor,
                    )
                    try:
                        snapshot_name = os.listdir(build)[0]
                        os.rename(
                            snapshot_name,
                            "moved-snapshot",
                            src_dir_fd=build,
                            dst_dir_fd=build,
                        )
                        os.mkdir(snapshot_name, mode=0o700, dir_fd=build)
                        MODULE.write_snapshot_file_at(
                            snapshot_descriptor,
                            "proof/source.txt",
                            b"descriptor anchored\n",
                        )
                    finally:
                        os.close(build)
            replacement = root / "build" / snapshot_name
            moved = root / "build" / "moved-snapshot"
            self.assertTrue(replacement.is_dir())
            self.assertTrue(moved.is_dir())
            self.assertEqual(list(moved.iterdir()), [])

    def test_sealed_snapshot_rejects_direct_source_write(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            descriptor = os.open(root, MODULE.directory_flags())
            try:
                MODULE.write_snapshot_file_at(
                    descriptor,
                    "src/source.txt",
                    b"sealed source\n",
                )
                certificates = MODULE.open_or_create_directory(
                    descriptor,
                    "certificates",
                    0o700,
                )
                os.close(certificates)
                MODULE.seal_snapshot(descriptor)
                with self.assertRaises(PermissionError):
                    source = os.open(
                        "src/source.txt",
                        os.O_WRONLY,
                        dir_fd=descriptor,
                    )
                    os.close(source)
            finally:
                MODULE.make_directories_writable(descriptor)
                os.close(descriptor)

    def test_fake_julia_fails_version_check_with_matching_hash(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            project = Path(name) / "project"
            runtime = Path(name) / "runtime"
            executable = runtime / "bin" / "julia"
            project.mkdir()
            (runtime / "bin").mkdir(parents=True)
            executable.write_text(
                "#!/usr/bin/python3\nprint('not-julia', end='')\n",
                encoding="ascii",
            )
            executable.chmod(0o755)
            expected = hashlib.sha256(executable.read_bytes()).hexdigest()
            tree = MODULE.stable_runtime_tree_sha256(runtime)
            with mock.patch.object(MODULE, "ROOT", project):
                with self.assertRaisesRegex(RuntimeError, "version mismatch"):
                    with MODULE.verified_julia_executable(
                        str(executable),
                        expected,
                        tree,
                        {"PATH": "/usr/bin:/bin"},
                    ):
                        pass

    def test_runtime_tree_digest_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            runtime = Path(name) / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin" / "julia").write_bytes(b"binary\n")
            before = MODULE.stable_runtime_tree_sha256(runtime)
            (runtime / "bin" / "julia").write_bytes(b"changed\n")
            after = MODULE.stable_runtime_tree_sha256(runtime)
            self.assertNotEqual(before, after)

    def test_julia_environment_rejects_loader_injection(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / ".julia").mkdir()
            descriptor = os.open(root, MODULE.directory_flags())
            try:
                with mock.patch.object(MODULE, "ROOT", root):
                    with mock.patch.dict(
                        os.environ,
                        {
                            "PATH": "/tmp/injected",
                            "LD_LIBRARY_PATH": "/tmp/injected",
                            "LD_AUDIT": "/tmp/audit.so",
                            "DYLD_INSERT_LIBRARIES": "/tmp/injected.dylib",
                            "HOME": "/safe/home",
                            "JULIA_NUM_THREADS": "2",
                        },
                        clear=True,
                    ):
                        environment = MODULE.julia_environment(descriptor)
            finally:
                os.close(descriptor)
            self.assertEqual(environment["HOME"], "/safe/home")
            self.assertEqual(environment["JULIA_NUM_THREADS"], "2")
            self.assertNotEqual(environment["PATH"], "/tmp/injected")
            self.assertNotIn("LD_LIBRARY_PATH", environment)
            self.assertNotIn("LD_AUDIT", environment)
            self.assertNotIn("DYLD_INSERT_LIBRARIES", environment)

    def test_snapshot_verifier_receives_captured_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            snapshot = Path(name)
            (snapshot / "verification").mkdir()
            witness = b"captured witness"
            manifest = (
                json.dumps(
                    {
                        "witness": {
                            "filename": MODULE.WITNESS_FILENAME,
                            "sha256": hashlib.sha256(witness).hexdigest(),
                            "size_bytes": len(witness),
                        }
                    },
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            descriptor = os.open(snapshot, MODULE.directory_flags())

            def inspect(command, **_kwargs):
                self.assertEqual(
                    (
                        snapshot
                        / "verification"
                        / MODULE.WITNESS_FILENAME
                    ).read_bytes(),
                    witness,
                )
                self.assertEqual(
                    (
                        snapshot
                        / "verification"
                        / MODULE.MANIFEST_FILENAME
                    ).read_bytes(),
                    manifest,
                )
                self.assertGreaterEqual(command.count("-I"), 2)
                self.assertGreaterEqual(command.count("-S"), 2)
                self.assertIn("-B", command)
                self.assertTrue(
                    any("runpy.run_path" in argument for argument in command)
                )
                return subprocess.CompletedProcess([], 0)

            try:
                with mock.patch.object(
                    MODULE.subprocess,
                    "run",
                    side_effect=inspect,
                ):
                    MODULE.verify_snapshot_package(
                        descriptor,
                        witness,
                        manifest,
                    )
            finally:
                MODULE.make_directories_writable(descriptor)
                os.close(descriptor)

    def test_compressed_package_gate_is_deterministic(self) -> None:
        witness = b"compressible witness bytes\n" * 100
        manifest = (
            json.dumps(
                {
                    "witness": {
                        "filename": MODULE.WITNESS_FILENAME,
                        "sha256": hashlib.sha256(witness).hexdigest(),
                        "size_bytes": len(witness),
                    }
                },
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        first = MODULE.compressed_package_metadata(witness, manifest)
        second = MODULE.compressed_package_metadata(witness, manifest)
        self.assertEqual(first, second)
        with mock.patch.object(
            MODULE,
            "MAX_COMPRESSED_PACKAGE_BYTES",
            first[0] - 1,
        ):
            with self.assertRaisesRegex(RuntimeError, "45 MiB"):
                MODULE.compressed_package_metadata(witness, manifest)


if __name__ == "__main__":
    unittest.main()
