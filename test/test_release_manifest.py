#!/usr/bin/env python3
"""Tests for stable repository-manifest hashing."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "release_manifest.py"
SPEC = importlib.util.spec_from_file_location("release_manifest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ReleaseManifestTests(unittest.TestCase):
    def test_stable_digest_matches_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "sample.txt"
            payload = b"stable release bytes\n"
            path.write_bytes(payload)
            with mock.patch.object(MODULE, "ROOT", root):
                self.assertEqual(
                    MODULE.digest("sample.txt"),
                    hashlib.sha256(payload).hexdigest(),
                )

    def test_digest_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "target.txt").write_text("target\n", encoding="ascii")
            (root / "link.txt").symlink_to("target.txt")
            with mock.patch.object(MODULE, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "cannot open"):
                    MODULE.digest("link.txt")

    def test_resolve_path_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with mock.patch.object(MODULE, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "unsafe"):
                    MODULE.resolve_path("../outside")

    def test_clean_commit_binding_accepts_exact_head(self) -> None:
        commit = "a" * 40
        with (
            mock.patch.object(MODULE, "require_repository_root"),
            mock.patch.object(
                MODULE,
                "current_commit",
                side_effect=[commit, commit],
            ),
            mock.patch.object(MODULE, "git_bytes", return_value=b""),
            mock.patch.object(MODULE, "git_returncode", return_value=0),
        ):
            self.assertEqual(MODULE.require_clean_commit(commit), commit)

    def test_clean_commit_binding_rejects_mismatch_and_dirty_tree(self) -> None:
        commit = "a" * 40
        with (
            mock.patch.object(MODULE, "require_repository_root"),
            mock.patch.object(MODULE, "current_commit", return_value="b" * 40),
        ):
            with self.assertRaisesRegex(RuntimeError, "mismatch"):
                MODULE.require_clean_commit(commit)
        with (
            mock.patch.object(MODULE, "require_repository_root"),
            mock.patch.object(MODULE, "current_commit", return_value=commit),
            mock.patch.object(
                MODULE,
                "git_bytes",
                return_value=b" M README.md\0",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "not clean"):
                MODULE.require_clean_commit(commit)

    def test_git_environment_removes_repository_redirection(self) -> None:
        with mock.patch.dict(
            MODULE.os.environ,
            {
                "GIT_DIR": "/tmp/redirected",
                "GIT_WORK_TREE": "/tmp/other",
                "PATH": "/usr/bin",
            },
            clear=True,
        ):
            environment = MODULE.git_environment()
        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("GIT_WORK_TREE", environment)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")

    def test_expected_manifest_can_be_derived_from_commit_blobs(self) -> None:
        payload = b"committed bytes\n"
        with (
            mock.patch.object(
                MODULE,
                "commit_tree_entries",
                return_value=(("sample.txt", "f" * 40),),
            ),
            mock.patch.object(MODULE, "git_bytes", return_value=payload),
        ):
            content = MODULE.expected_from_commit("a" * 40)
        self.assertEqual(
            content,
            f"{hashlib.sha256(payload).hexdigest()}  sample.txt\n",
        )

    def test_real_git_commit_tree_binding_ignores_redirect_environment(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "init", "-q"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    str(MODULE.GIT_EXECUTABLE),
                    "config",
                    "user.name",
                    "Release Test",
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    str(MODULE.GIT_EXECUTABLE),
                    "config",
                    "user.email",
                    "release-test@example.invalid",
                ],
                cwd=root,
                check=True,
            )
            payload = b"committed release bytes\n"
            (root / "sample.txt").write_bytes(payload)
            subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "add", "sample.txt"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "commit", "-q", "-m", "sample"],
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
            (root / "sample.txt").write_bytes(b"replacement bytes\n")
            subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "add", "sample.txt"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    str(MODULE.GIT_EXECUTABLE),
                    "commit",
                    "-q",
                    "-m",
                    "replacement",
                ],
                cwd=root,
                check=True,
            )
            replacement = subprocess.run(
                [str(MODULE.GIT_EXECUTABLE), "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            subprocess.run(
                [
                    str(MODULE.GIT_EXECUTABLE),
                    "checkout",
                    "-q",
                    "--detach",
                    commit,
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    str(MODULE.GIT_EXECUTABLE),
                    "update-ref",
                    f"refs/replace/{commit}",
                    replacement,
                ],
                cwd=root,
                check=True,
            )

            with (
                mock.patch.object(MODULE, "ROOT", root),
                mock.patch.object(
                    MODULE,
                    "MANIFEST",
                    root / "release-manifest.sha256",
                ),
                mock.patch.dict(
                    MODULE.os.environ,
                    {
                        "GIT_DIR": "/tmp/redirected",
                        "GIT_WORK_TREE": "/tmp/redirected-worktree",
                    },
                    clear=False,
                ),
            ):
                self.assertEqual(MODULE.require_clean_commit(commit), commit)
                self.assertEqual(
                    MODULE.expected_from_commit(commit),
                    f"{hashlib.sha256(payload).hexdigest()}  sample.txt\n",
                )


if __name__ == "__main__":
    unittest.main()
