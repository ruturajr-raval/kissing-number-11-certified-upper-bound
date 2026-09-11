#!/usr/bin/env python3
"""Run a command with process-tree wall-time and resident-memory limits."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


PS_EXECUTABLE = "/bin/ps"
SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"


def process_table() -> dict[int, tuple[int, int]]:
    result = subprocess.run(
        [PS_EXECUTABLE, "-axo", "pid=,ppid=,rss="],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    table: dict[int, tuple[int, int]] = {}
    for line_number, line in enumerate(result.stdout.splitlines(), 1):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 3:
            raise ValueError(f"malformed ps row {line_number}: {line!r}")
        try:
            pid, parent, rss_kib = (int(field) for field in fields)
        except ValueError as exc:
            raise ValueError(
                f"noninteger ps row {line_number}: {line!r}"
            ) from exc
        if pid <= 0 or parent < 0 or rss_kib < 0:
            raise ValueError(f"invalid ps row {line_number}: {line!r}")
        if pid in table:
            raise ValueError(f"duplicate PID in ps output: {pid}")
        table[pid] = (parent, rss_kib)
    return table


def process_tree_rss_kib(root_pid: int) -> int:
    table = process_table()
    if root_pid not in table:
        raise ValueError(f"supervised root PID {root_pid} is absent from ps output")
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (parent, _) in table.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sum(table[pid][1] for pid in descendants)


def child_environment(profile: str) -> dict[str, str] | None:
    if profile == "inherit":
        return None
    if profile not in {"certificate-export", "numerical-solve"}:
        raise ValueError(f"unsupported environment profile: {profile}")
    allowed = {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "TMPDIR",
        "TZ",
        "JULIA",
        "JULIA_NUM_THREADS",
        "KN11_EXPECTED_EXACT_INPUT_SHA256",
        "KN11_EXPECTED_JULIA_SHA256",
        "KN11_EXPECTED_JULIA_TREE_SHA256",
    }
    if profile == "numerical-solve":
        allowed = {
            "HOME",
            "KN11_CHECKPOINT_SECONDS",
            "KN11_EXACT_OUTPUT",
            "KN11_FIXED_CHECKPOINT",
            "KN11_FIXED_OUTPUT",
            "KN11_MAX_ITERATIONS",
            "KN11_MAX_OBJECTIVE_ERROR",
            "KN11_MAX_RESIDUAL",
            "KN11_MIN_EIGENVALUE",
            "KN11_NUMERICAL_CHECKPOINT",
            "KN11_NUMERICAL_OUTPUT",
            "KN11_ORIGINAL_FIXED_CHECKPOINT",
            "KN11_PRECISION",
            "KN11_PROJECTION_OUTPUT",
            "KN11_RESUME_FIXED_CHECKPOINT",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TERM",
            "TMPDIR",
            "TZ",
        }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in allowed
    }
    environment["PATH"] = SAFE_PATH
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONSAFEPATH"] = "1"
    return environment


def terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    if process.poll() is None:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    if process.poll() is None:
        process.wait()


def copy_output(stream, log_stream) -> None:
    read_block = getattr(stream, "read1", stream.read)
    for block in iter(lambda: read_block(64 * 1024), b""):
        sys.stdout.buffer.write(block)
        sys.stdout.buffer.flush()
        log_stream.write(block)
        log_stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wall-seconds", type=float, required=True)
    parser.add_argument("--rss-gib", type=float, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument(
        "--environment-profile",
        choices=("inherit", "certificate-export", "numerical-solve"),
        default="inherit",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    args.log.parent.mkdir(parents=True, exist_ok=True)
    maximum_rss_kib = int(args.rss_gib * 1024 * 1024)
    with args.log.open("ab") as log_stream:
        interrupted_by: list[int] = []

        def record_signal(signum, _frame) -> None:
            if not interrupted_by:
                interrupted_by.append(signum)

        signal.signal(signal.SIGINT, record_signal)
        signal.signal(signal.SIGTERM, record_signal)
        process: subprocess.Popen[bytes] | None = None
        output_thread: threading.Thread | None = None
        try:
            process = subprocess.Popen(
                command,
                env=child_environment(args.environment_profile),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            assert process.stdout is not None
            output_thread = threading.Thread(
                target=copy_output,
                args=(process.stdout, log_stream),
                daemon=True,
            )
            output_thread.start()
            started = time.monotonic()
            exit_code = 0
            while process.poll() is None:
                if interrupted_by:
                    signum = interrupted_by[0]
                    print(
                        f"received signal {signum}; terminating process tree",
                        file=sys.stderr,
                    )
                    terminate_group(process)
                    exit_code = 128 + signum
                    break

                elapsed = time.monotonic() - started
                try:
                    rss_kib = process_tree_rss_kib(process.pid)
                except (OSError, ValueError, subprocess.CalledProcessError) as exc:
                    if process.poll() is not None:
                        break
                    print(
                        "cannot measure process-tree resident memory; "
                        f"terminating fail-closed: {exc}",
                        file=sys.stderr,
                    )
                    terminate_group(process)
                    exit_code = 125
                    break
                if elapsed > args.wall_seconds:
                    print(
                        f"wall-time limit exceeded after {elapsed:.1f} seconds",
                        file=sys.stderr,
                    )
                    terminate_group(process)
                    exit_code = 124
                    break
                if rss_kib > maximum_rss_kib:
                    print(
                        "resident-memory limit exceeded at "
                        f"{rss_kib / 1024**2:.2f} GiB",
                        file=sys.stderr,
                    )
                    terminate_group(process)
                    exit_code = 137
                    break
                time.sleep(1)

            if exit_code == 0:
                exit_code = process.wait()
            return exit_code
        finally:
            if process is not None:
                terminate_group(process)
            if output_thread is not None:
                output_thread.join(timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
