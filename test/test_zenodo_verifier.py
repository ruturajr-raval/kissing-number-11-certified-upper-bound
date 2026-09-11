from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "verify_zenodo_record.py"
SPEC = importlib.util.spec_from_file_location("verify_zenodo_record", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load Zenodo verifier module")
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


class ZenodoVerifierTests(unittest.TestCase):
    def test_local_inventory_requires_paper_certificate_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            files = {
                "paper.pdf": b"%PDF-paper",
                "source.tar.gz": b"source",
                "certificate.tar.gz": b"certificate",
            }
            for name, data in files.items():
                (directory / name).write_bytes(data)
            (directory / "SHA256SUMS").write_text(
                "".join(
                    f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                    for name, data in sorted(files.items())
                ),
                encoding="ascii",
            )
            inventory = verifier.local_inventory(directory)
            self.assertEqual(
                set(inventory),
                {
                    "SHA256SUMS",
                    "paper.pdf",
                    "source.tar.gz",
                    "certificate.tar.gz",
                },
            )

    def test_remote_entries_support_current_zenodo_schema(self) -> None:
        record = {
            "files": {
                "entries": {
                    "paper.pdf": {
                        "size": 12,
                        "links": {"content": "https://example.test/paper"},
                    }
                }
            }
        }
        self.assertEqual(
            verifier.remote_entries(record),
            {"paper.pdf": (12, "https://example.test/paper")},
        )

    def test_record_metadata_matches_release_identity(self) -> None:
        record = {
            "id": 123,
            "doi": "10.5281/zenodo.123",
            "conceptrecid": "122",
            "metadata": {
                "title": "Example title",
                "version": "0.1.0",
                "publication_date": "2026-09-11",
                "resource_type": {"type": "software"},
                "description": "Example &lt;= description.",
                "rights": [{"id": "mit"}],
                "subjects": [
                    {"subject": "kissing number"},
                    {"subject": "exact certification"},
                ],
                "creators": [
                    {
                        "person_or_org": {
                            "family_name": "Raval",
                            "given_name": "Ruturaj R",
                            "identifiers": [
                                {
                                    "scheme": "orcid",
                                    "identifier": "0000-0003-4930-8981",
                                }
                            ],
                        },
                        "affiliations": [
                            {"name": "Independent Researcher"}
                        ],
                    }
                ],
                "related_identifiers": [
                    {
                        "identifier": (
                            "https://github.com/example/releases/tag/v0.1.0"
                        ),
                        "relation_type": {"id": "issupplementto"},
                        "scheme": "url",
                    }
                ],
            },
        }
        expected = {
            "title": "Example title",
            "version": "0.1.0",
            "publication_date": "2026-09-11",
            "upload_type": "software",
            "description": "Example <= description.",
            "license": "MIT",
            "keywords": [
                "exact certification",
                "kissing number",
            ],
            "creators": [
                {
                    "name": "Raval, Ruturaj R",
                    "affiliation": "Independent Researcher",
                    "orcid": "0000-0003-4930-8981",
                }
            ],
            "related_identifiers": [
                {
                    "identifier": (
                        "https://github.com/example/releases/tag/v0.1.0"
                    ),
                    "relation": "isSupplementTo",
                    "scheme": "url",
                }
            ],
        }
        claim = {
            "doi": {
                "version": "10.5281/zenodo.123",
                "concept": "10.5281/zenodo.122",
            }
        }
        verifier.verify_record_metadata(record, expected, claim, "123")

    def test_record_metadata_rejects_affiliation_mismatch(self) -> None:
        record = {
            "id": 1,
            "doi": "10.5281/zenodo.1",
            "conceptdoi": "10.5281/zenodo.2",
            "metadata": {
                "title": "Title",
                "version": "1.0.0",
                "publication_date": "2026-09-11",
                "resource_type": {"id": "software"},
                "description": "Description",
                "rights": [{"id": "mit"}],
                "subjects": [{"subject": "test"}],
                "creators": [
                    {
                        "person_or_org": {
                            "family_name": "Raval",
                            "given_name": "Ruturaj R",
                            "identifiers": [
                                {
                                    "scheme": "orcid",
                                    "identifier": "0000-0003-4930-8981",
                                }
                            ],
                        },
                        "affiliations": [{"name": "Wrong affiliation"}],
                    }
                ],
                "related_identifiers": [
                    {
                        "identifier": "https://example.test/v1.0.0",
                        "relation_type": {"id": "issupplementto"},
                        "scheme": "url",
                    }
                ],
            },
        }
        expected = {
            "title": "Title",
            "version": "1.0.0",
            "publication_date": "2026-09-11",
            "upload_type": "software",
            "description": "Description",
            "license": "MIT",
            "keywords": ["test"],
            "creators": [
                {
                    "name": "Raval, Ruturaj R",
                    "affiliation": "Independent Researcher",
                    "orcid": "0000-0003-4930-8981",
                }
            ],
            "related_identifiers": [
                {
                    "identifier": "https://example.test/v1.0.0",
                    "relation": "isSupplementTo",
                    "scheme": "url",
                }
            ],
        }
        claim = {
            "doi": {
                "version": "10.5281/zenodo.1",
                "concept": "10.5281/zenodo.2",
            }
        }
        with self.assertRaisesRegex(ValueError, "affiliation"):
            verifier.verify_record_metadata(record, expected, claim, "1")


if __name__ == "__main__":
    unittest.main()
