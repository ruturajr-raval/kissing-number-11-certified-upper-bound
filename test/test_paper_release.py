from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PaperReleaseTests(unittest.TestCase):
    def test_release_pdf_record_matches_tracked_files(self) -> None:
        record = json.loads(
            (ROOT / "paper/release-pdf.json").read_text(encoding="utf-8")
        )
        source = ROOT / record["source"]["path"]
        pdf = ROOT / record["pdf"]["path"]
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(sha256(source), record["source"]["sha256"])
        self.assertEqual(sha256(pdf), record["pdf"]["sha256"])
        self.assertEqual(pdf.stat().st_size, record["pdf"]["bytes"])
        self.assertEqual(pdf.read_bytes()[:5], b"%PDF-")
        self.assertEqual(record["pdf"]["pages"], 4)
        self.assertEqual(record["build"]["engine"], "Tectonic 0.17.0")
        self.assertEqual(
            record["build"]["bundle_digest"],
            "6ffe055852f8faf66c0acbe1a7fb27f87b869a90bad1204f3bf4d9683f597c7c",
        )
        self.assertEqual(record["build"]["source_date_epoch"], 1789084800)
        self.assertEqual(record["inspection"]["date"], "2026-09-11")
        self.assertEqual(record["inspection"]["pages_inspected"], 4)
        self.assertEqual(record["inspection"]["result"], "pass")


if __name__ == "__main__":
    unittest.main()
