#!/usr/bin/env python3
"""Adversarial tests for the process-tree resource supervisor."""

from __future__ import annotations

import os
from pathlib import Path
import importlib.util
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "tools" / "run_with_limits.py"
BUILD = ROOT / "build"
SPEC = importlib.util.spec_from_file_location("run_with_limits", SUPERVISOR)
assert SPEC is not None and SPEC.loader is not None
SUPERVISOR_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPERVISOR_MODULE)


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_for_file(path: Path, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and path.read_text(encoding="ascii").strip():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")


def wait_for_exit(pid: int, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.05)
    raise AssertionError(f"process {pid} survived supervisor shutdown")


class ResourceSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        BUILD.mkdir(parents=True, exist_ok=True)

    def command(self, directory: Path, wall_seconds: str) -> list[str]:
        pid_file = directory / "child.pid"
        child = (
            "from pathlib import Path; "
            "import os,time; "
            f"Path({str(pid_file)!r}).write_text(str(os.getpid()), encoding='ascii'); "
            "time.sleep(60)"
        )
        return [
            sys.executable,
            str(SUPERVISOR),
            "--wall-seconds",
            wall_seconds,
            "--rss-gib",
            "1",
            "--log",
            str(directory / "run.log"),
            "--",
            sys.executable,
            "-c",
            child,
        ]

    def test_wall_limit_kills_child_group(self) -> None:
        with tempfile.TemporaryDirectory(dir=BUILD) as name:
            directory = Path(name)
            result = subprocess.run(
                self.command(directory, "0.2"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
            self.assertEqual(result.returncode, 124)
            pid = int((directory / "child.pid").read_text(encoding="ascii"))
            wait_for_exit(pid)

    def test_process_table_failure_is_not_silently_zero(self) -> None:
        with mock.patch.object(
            SUPERVISOR_MODULE.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["ps"]),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                SUPERVISOR_MODULE.process_tree_rss_kib(os.getpid())

    def test_process_table_uses_absolute_ps(self) -> None:
        completed = subprocess.CompletedProcess(
            [SUPERVISOR_MODULE.PS_EXECUTABLE],
            0,
            stdout=f"{os.getpid()} {os.getppid()} 2048\n",
        )
        with mock.patch.object(
            SUPERVISOR_MODULE.subprocess,
            "run",
            return_value=completed,
        ) as run:
            SUPERVISOR_MODULE.process_table()
        self.assertEqual(
            run.call_args.args[0][0],
            SUPERVISOR_MODULE.PS_EXECUTABLE,
        )

    def test_certificate_export_environment_is_allowlisted(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "PATH": "/tmp/injected",
                "PYTHONPATH": "/tmp/injected",
                "DYLD_INSERT_LIBRARIES": "/tmp/injected.dylib",
                "JULIA": "/safe/julia",
                "KN11_EXPECTED_JULIA_SHA256": "a" * 64,
            },
            clear=True,
        ):
            environment = SUPERVISOR_MODULE.child_environment(
                "certificate-export"
            )
        assert environment is not None
        self.assertEqual(environment["PATH"], SUPERVISOR_MODULE.SAFE_PATH)
        self.assertEqual(environment["JULIA"], "/safe/julia")
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("DYLD_INSERT_LIBRARIES", environment)

    def test_numerical_environment_removes_loader_injection(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "PATH": "/tmp/injected",
                "LD_LIBRARY_PATH": "/tmp/injected",
                "LD_AUDIT": "/tmp/audit.so",
                "DYLD_INSERT_LIBRARIES": "/tmp/injected.dylib",
                "HOME": "/safe/home",
                "KN11_PROJECTION_OUTPUT": "/safe/projected.jls",
            },
            clear=True,
        ):
            environment = SUPERVISOR_MODULE.child_environment(
                "numerical-solve"
            )
        assert environment is not None
        self.assertEqual(environment["PATH"], SUPERVISOR_MODULE.SAFE_PATH)
        self.assertEqual(environment["HOME"], "/safe/home")
        self.assertEqual(
            environment["KN11_PROJECTION_OUTPUT"],
            "/safe/projected.jls",
        )
        self.assertNotIn("LD_LIBRARY_PATH", environment)
        self.assertNotIn("LD_AUDIT", environment)
        self.assertNotIn("DYLD_INSERT_LIBRARIES", environment)

    def test_missing_root_pid_is_rejected(self) -> None:
        completed = subprocess.CompletedProcess(
            ["ps"],
            0,
            stdout="101 1 2048\n",
        )
        with mock.patch.object(
            SUPERVISOR_MODULE.subprocess,
            "run",
            return_value=completed,
        ):
            with self.assertRaisesRegex(ValueError, "root PID"):
                SUPERVISOR_MODULE.process_tree_rss_kib(202)

    def test_malformed_process_table_row_is_rejected(self) -> None:
        completed = subprocess.CompletedProcess(
            ["ps"],
            0,
            stdout="101 1\n",
        )
        with mock.patch.object(
            SUPERVISOR_MODULE.subprocess,
            "run",
            return_value=completed,
        ):
            with self.assertRaisesRegex(ValueError, "malformed ps row"):
                SUPERVISOR_MODULE.process_table()

    def test_short_command_exit_is_not_a_measurement_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir=BUILD) as name:
            directory = Path(name)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SUPERVISOR),
                    "--wall-seconds",
                    "5",
                    "--rss-gib",
                    "1",
                    "--log",
                    str(directory / "short.log"),
                    "--",
                    sys.executable,
                    "-c",
                    "pass",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_interrupt_kills_child_group(self) -> None:
        with tempfile.TemporaryDirectory(dir=BUILD) as name:
            directory = Path(name)
            wrapper = subprocess.Popen(
                self.command(directory, "60"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            pid_file = directory / "child.pid"
            wait_for_file(pid_file)
            child_pid = int(pid_file.read_text(encoding="ascii"))
            wrapper.send_signal(signal.SIGINT)
            wrapper.communicate(timeout=15)
            self.assertEqual(wrapper.returncode, 128 + signal.SIGINT)
            wait_for_exit(child_pid)


if __name__ == "__main__":
    unittest.main()
