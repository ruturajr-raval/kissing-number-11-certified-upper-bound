#!/usr/bin/env python3
"""Tests for shell-free trust-anchor release orchestration."""

from __future__ import annotations

from contextlib import nullcontext
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "release_check.py"
SPEC = importlib.util.spec_from_file_location("release_check", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ReleaseCheckTests(unittest.TestCase):
    def anchors(self) -> MODULE.ReleaseAnchors:
        return MODULE.ReleaseAnchors(
            manifest="a" * 64,
            witness="b" * 64,
            source_specification="c" * 64,
            rounding_specification="d" * 64,
            verification_specification="1" * 64,
            commit="e" * 40,
            julia="f" * 64,
            julia_tree="0" * 64,
        )

    def test_anchor_loader_rejects_shell_text(self) -> None:
        environment = {
            MODULE.MANIFEST_ENV: "a" * 64 + "; true",
            MODULE.WITNESS_ENV: "b" * 64,
            MODULE.SOURCE_ENV: "c" * 64,
            MODULE.ROUNDING_ENV: "d" * 64,
            MODULE.VERIFICATION_ENV: "1" * 64,
            MODULE.COMMIT_ENV: "e" * 40,
            MODULE.JULIA_ENV: "f" * 64,
            MODULE.JULIA_TREE_ENV: "0" * 64,
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "malformed"):
                MODULE.load_anchors(
                    require_commit=True,
                    require_julia=True,
                )

    def test_authoritative_bootstrap_starts_outside_worktree(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="ascii")
        documentation = (
            ROOT / "docs" / "REPRODUCIBILITY.md"
        ).read_text(encoding="ascii")
        self.assertIn(
            "authoritative release verification must start outside the worktree",
            makefile,
        )
        self.assertIn("/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C", documentation)
        self.assertIn("/bin/zsh -f -c", documentation)
        self.assertNotIn("make release-check \\", documentation)
        self.assertLess(
            documentation.index("/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C"),
            documentation.index("/bin/zsh -f -c"),
        )

    def test_release_environment_removes_command_overrides(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "GIT_DIR": "/tmp/redirected",
                "MAKE": "true",
                "MAKEFLAGS": "--eval=bad",
                "PYTHON": "true",
                "PYTHONPATH": "/tmp/injected",
                "CXX": "true",
                "CPATH": "/tmp/injected-headers",
                "LIBRARY_PATH": "/tmp/injected-libraries",
            },
            clear=True,
        ):
            environment = MODULE.release_environment()
        for name in (
            "GIT_DIR",
            "MAKE",
            "MAKEFLAGS",
            "PYTHON",
            "PYTHONPATH",
            "CXX",
            "CPATH",
            "LIBRARY_PATH",
        ):
            self.assertNotIn(name, environment)

    def test_certificate_command_uses_discrete_anchor_arguments(self) -> None:
        anchors = self.anchors()
        command = MODULE.certificate_check_command(anchors)
        self.assertIsInstance(command, list)
        self.assertEqual(command[command.index("--expected-manifest-sha256") + 1], anchors.manifest)
        self.assertEqual(command[command.index("--expected-witness-sha256") + 1], anchors.witness)
        self.assertEqual(
            command[
                command.index("--expected-verification-specification") + 1
            ],
            anchors.verification_specification,
        )
        self.assertNotIn("sh", command)
        self.assertNotIn("-c", command)

    def test_full_gate_orders_precheck_tests_replay_and_postcheck(self) -> None:
        anchors = self.anchors()
        calls: list[list[str]] = []
        commit_checks: list[str] = []
        julia = Path("/safe/julia")
        with (
            mock.patch.object(
                MODULE,
                "verified_julia",
                return_value=nullcontext(julia),
            ),
            mock.patch.object(
                MODULE,
                "run_commit_manifest_check",
                side_effect=lambda commit, _environment: commit_checks.append(
                    commit
                ),
            ),
            mock.patch.object(MODULE, "verify_certificate_files"),
            mock.patch.object(
                MODULE,
                "run_checked",
                side_effect=lambda command, _environment: calls.append(command),
            ),
        ):
            MODULE.run_full_release_check(anchors, {})
        repository_checks = MODULE.repository_check_commands(julia)
        dependency_check = MODULE.julia_command(
            julia,
            "scripts/verify_dependency_integrity.jl",
        )
        self.assertEqual(repository_checks[0], dependency_check)
        self.assertEqual(repository_checks[-2], dependency_check)
        self.assertEqual(
            repository_checks[-1],
            MODULE.worktree_manifest_check_command(),
        )
        self.assertEqual(
            repository_checks[1],
            MODULE.julia_command(julia, "test/runtests.jl"),
        )
        self.assertIn(
            MODULE.julia_command(
                julia,
                "scripts/smoke_exact_rounding.jl",
            ),
            repository_checks,
        )
        self.assertEqual(calls[: len(repository_checks)], repository_checks)
        self.assertEqual(
            calls[len(repository_checks)],
            MODULE.certificate_check_command(anchors),
        )
        self.assertEqual(commit_checks, [anchors.commit, anchors.commit])

    def test_isolated_interpreter_is_required(self) -> None:
        with mock.patch.object(
            MODULE.sys,
            "flags",
            SimpleNamespace(
                isolated=0,
                ignore_environment=0,
                no_user_site=0,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "-I -E -s"):
                MODULE.require_isolated_interpreter()

    def test_fake_julia_fails_version_check_even_with_matching_hash(self) -> None:
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
                    with MODULE.verified_julia(
                        str(executable),
                        expected,
                        tree,
                        MODULE.release_environment(),
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

    def test_commit_manifest_check_uses_expected_commit_script(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            tools = root / "tools"
            tools.mkdir()
            script = tools / "release_manifest.py"
            script.write_text(
                "import argparse\n"
                "from pathlib import Path\n"
                "parser = argparse.ArgumentParser()\n"
                "parser.add_argument('--repository-root', required=True)\n"
                "parser.add_argument('--check', action='store_true')\n"
                "parser.add_argument('--require-clean', action='store_true')\n"
                "parser.add_argument('--expected-commit', required=True)\n"
                "args = parser.parse_args()\n"
                "Path(args.repository_root, 'commit-script-ran').write_text(\n"
                "    args.expected_commit, encoding='ascii')\n",
                encoding="ascii",
            )
            subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "init", "-q"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    str(MODULE.GIT_EXECUTABLE),
                    "config",
                    "user.email",
                    "test@example.invalid",
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    str(MODULE.GIT_EXECUTABLE),
                    "config",
                    "user.name",
                    "Test",
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "add", "tools/release_manifest.py"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "commit", "-qm", "fixture"],
                cwd=root,
                check=True,
            )
            commit = subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            script.write_text(
                "raise RuntimeError('mutable worktree script executed')\n",
                encoding="ascii",
            )
            with mock.patch.object(MODULE, "ROOT", root):
                MODULE.run_commit_manifest_check(
                    commit,
                    MODULE.release_environment(),
                )
            self.assertEqual(
                (root / "commit-script-ran").read_text(encoding="ascii"),
                commit,
            )

    def test_certificate_mutation_after_replay_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            certificates = root / "certificates"
            certificates.mkdir()
            manifest = b"manifest\n"
            witness = b"witness\n"
            manifest_path = certificates / "kn11-degree17-certificate-v2.json"
            witness_path = certificates / "kn11-degree17-witness-v2.bin"
            manifest_path.write_bytes(manifest)
            witness_path.write_bytes(witness)
            anchors = MODULE.ReleaseAnchors(
                manifest=hashlib.sha256(manifest).hexdigest(),
                witness=hashlib.sha256(witness).hexdigest(),
                source_specification="c" * 64,
                rounding_specification="d" * 64,
                verification_specification="1" * 64,
                commit=None,
                julia=None,
                julia_tree=None,
            )

            def mutate(_command, _environment) -> None:
                witness_path.write_bytes(b"changed\n")

            with (
                mock.patch.object(MODULE, "ROOT", root),
                mock.patch.object(MODULE, "run_checked", side_effect=mutate),
            ):
                with self.assertRaisesRegex(RuntimeError, "witness"):
                    MODULE.run_certificate_check(anchors, {})


if __name__ == "__main__":
    unittest.main()
