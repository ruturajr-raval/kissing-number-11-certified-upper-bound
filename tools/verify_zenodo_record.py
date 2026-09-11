#!/usr/bin/env python3
"""Verify a Zenodo record against the exact local release assets."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
from typing import BinaryIO
from urllib.request import Request, urlopen


CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)$")


def sha256_stream(stream: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
        size += len(block)
    return size, digest.hexdigest()


def sha256_file(path: Path) -> tuple[int, str]:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def local_inventory(release_dir: Path) -> dict[str, tuple[int, str]]:
    checksums_path = release_dir / "SHA256SUMS"
    if not checksums_path.is_file() or checksums_path.is_symlink():
        raise ValueError("release directory has no safe SHA256SUMS")
    expected: dict[str, tuple[int, str]] = {}
    for line_number, line in enumerate(
        checksums_path.read_text(encoding="ascii").splitlines(),
        start=1,
    ):
        match = CHECKSUM_RE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid checksum line {line_number}")
        digest, name = match.groups()
        if name in expected:
            raise ValueError(f"duplicate checksum entry: {name}")
        path = release_dir / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"local release asset is missing or unsafe: {name}")
        size, observed_digest = sha256_file(path)
        if observed_digest != digest:
            raise ValueError(f"local release hash mismatch: {name}")
        expected[name] = (size, digest)
    expected["SHA256SUMS"] = sha256_file(checksums_path)
    if len(expected) != 4:
        raise ValueError("release inventory must contain exactly four files")
    if not any(name.endswith(".pdf") for name in expected):
        raise ValueError("release inventory has no standalone paper PDF")
    if not any("certificate" in name and name.endswith(".tar.gz") for name in expected):
        raise ValueError("release inventory has no certificate archive")
    return expected


def remote_entries(record: dict[str, object]) -> dict[str, tuple[int, str]]:
    files = record.get("files")
    if isinstance(files, dict) and isinstance(files.get("entries"), dict):
        entries = files["entries"]
        result: dict[str, tuple[int, str]] = {}
        for name, raw in entries.items():
            if not isinstance(name, str) or not isinstance(raw, dict):
                raise ValueError("invalid Zenodo file entry")
            links = raw.get("links")
            if not isinstance(links, dict):
                raise ValueError(f"Zenodo file has no links: {name}")
            url = links.get("content") or links.get("self")
            size = raw.get("size")
            if not isinstance(url, str) or not isinstance(size, int):
                raise ValueError(f"incomplete Zenodo file metadata: {name}")
            result[name] = (size, url)
        return result
    if isinstance(files, list):
        result = {}
        for raw in files:
            if not isinstance(raw, dict):
                raise ValueError("invalid legacy Zenodo file entry")
            name = raw.get("key") or raw.get("filename")
            links = raw.get("links")
            if not isinstance(name, str) or not isinstance(links, dict):
                raise ValueError("invalid legacy Zenodo file metadata")
            url = links.get("self") or links.get("download")
            size = raw.get("size") or raw.get("filesize")
            if not isinstance(url, str) or not isinstance(size, int):
                raise ValueError(f"incomplete Zenodo file metadata: {name}")
            result[name] = (size, url)
        return result
    raise ValueError("Zenodo record has no supported file inventory")


def _normalized_license(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.endswith("-license"):
        normalized = normalized[: -len("-license")]
    return normalized


def _normalized_identifier_type(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("id") or value.get("type") or value.get("title")
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _creator_name(creator: dict[str, object]) -> str | None:
    name = creator.get("name")
    if isinstance(name, str):
        return name
    person = creator.get("person_or_org")
    if not isinstance(person, dict):
        return None
    family_name = str(person.get("family_name") or "").strip()
    given_name = str(person.get("given_name") or "").strip()
    if not family_name or not given_name:
        return None
    return f"{family_name}, {given_name}"


def _creator_affiliations(creator: dict[str, object]) -> set[str]:
    affiliations: set[str] = set()
    legacy = creator.get("affiliation")
    if isinstance(legacy, str) and legacy.strip():
        affiliations.add(legacy.strip())
    current = creator.get("affiliations")
    if isinstance(current, list):
        for item in current:
            if isinstance(item, str) and item.strip():
                affiliations.add(item.strip())
            elif isinstance(item, dict):
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    affiliations.add(name.strip())
    return affiliations


def _creator_orcid(creator: dict[str, object]) -> str | None:
    orcid = creator.get("orcid")
    if isinstance(orcid, str):
        return orcid.removeprefix("https://orcid.org/")
    person = creator.get("person_or_org")
    if not isinstance(person, dict):
        return None
    identifiers = person.get("identifiers")
    if not isinstance(identifiers, list):
        return None
    for identifier in identifiers:
        if (
            isinstance(identifier, dict)
            and identifier.get("scheme") == "orcid"
            and isinstance(identifier.get("identifier"), str)
        ):
            return identifier["identifier"].removeprefix("https://orcid.org/")
    return None


def _observed_keywords(metadata: dict[str, object]) -> list[str]:
    keywords = metadata.get("keywords")
    if isinstance(keywords, list) and all(
        isinstance(keyword, str) for keyword in keywords
    ):
        return sorted(keywords)
    subjects = metadata.get("subjects")
    if not isinstance(subjects, list):
        return []
    return sorted(
        subject["subject"]
        for subject in subjects
        if isinstance(subject, dict)
        and isinstance(subject.get("subject"), str)
    )


def _related_identity(item: dict[str, object]) -> tuple[str, str, str]:
    relation = item.get("relation")
    if relation is None:
        relation = item.get("relation_type")
    return (
        str(item.get("identifier") or ""),
        _normalized_identifier_type(relation),
        _normalized_identifier_type(item.get("scheme")),
    )


def verify_record_metadata(
    record: dict[str, object],
    expected_metadata: dict[str, object],
    claim: dict[str, object],
    record_id: str,
) -> None:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Zenodo record has no metadata")
    observed_id = record.get("id") or record.get("recid")
    if str(observed_id) != str(record_id):
        raise ValueError("Zenodo record ID mismatch")

    for field in ("title", "version", "publication_date"):
        if metadata.get(field) != expected_metadata.get(field):
            raise ValueError(f"Zenodo metadata mismatch: {field}")

    observed_resource_type = metadata.get("upload_type")
    if observed_resource_type is None:
        observed_resource_type = metadata.get("resource_type")
    if _normalized_identifier_type(
        observed_resource_type
    ) != _normalized_identifier_type(expected_metadata.get("upload_type")):
        raise ValueError("Zenodo resource type mismatch")

    description = metadata.get("description")
    if (
        not isinstance(description, str)
        or html.unescape(description) != expected_metadata.get("description")
    ):
        raise ValueError("Zenodo description mismatch")
    expected_keywords = expected_metadata.get("keywords")
    if not isinstance(expected_keywords, list) or not all(
        isinstance(keyword, str) for keyword in expected_keywords
    ):
        raise ValueError("local Zenodo metadata has invalid keywords")
    if _observed_keywords(metadata) != sorted(expected_keywords):
        raise ValueError("Zenodo keywords mismatch")

    doi = claim.get("doi")
    if not isinstance(doi, dict):
        raise ValueError("claim record has no DOI metadata")
    observed_version_doi = (
        record.get("doi")
        or metadata.get("doi")
        or (
            record.get("pids", {}).get("doi", {}).get("identifier")
            if isinstance(record.get("pids"), dict)
            else None
        )
    )
    observed_concept_doi = record.get("conceptdoi")
    if observed_concept_doi is None and record.get("conceptrecid"):
        observed_concept_doi = f"10.5281/zenodo.{record.get('conceptrecid')}"
    if observed_concept_doi is None:
        parent = record.get("parent")
        if isinstance(parent, dict):
            pids = parent.get("pids")
            if isinstance(pids, dict) and isinstance(pids.get("doi"), dict):
                observed_concept_doi = pids["doi"].get("identifier")
    if observed_version_doi != doi.get("version"):
        raise ValueError("Zenodo version DOI mismatch")
    if observed_concept_doi != doi.get("concept"):
        raise ValueError("Zenodo concept DOI mismatch")

    expected_creators = expected_metadata.get("creators")
    observed_creators = metadata.get("creators")
    if not isinstance(expected_creators, list) or not expected_creators:
        raise ValueError("local Zenodo metadata has no creator")
    if (
        not isinstance(observed_creators, list)
        or len(observed_creators) != len(expected_creators)
    ):
        raise ValueError("Zenodo creator count mismatch")
    for expected_creator, observed_creator in zip(
        expected_creators,
        observed_creators,
    ):
        if not isinstance(expected_creator, dict) or not isinstance(
            observed_creator,
            dict,
        ):
            raise ValueError("invalid creator metadata")
        if _creator_name(observed_creator) != expected_creator.get("name"):
            raise ValueError("Zenodo creator name mismatch")
        if expected_creator.get("affiliation") not in _creator_affiliations(
            observed_creator
        ):
            raise ValueError("Zenodo creator affiliation mismatch")
        expected_orcid = str(expected_creator.get("orcid") or "").removeprefix(
            "https://orcid.org/"
        )
        if _creator_orcid(observed_creator) != expected_orcid:
            raise ValueError("Zenodo creator ORCID mismatch")

    expected_license = expected_metadata.get("license")
    observed_license = metadata.get("license")
    if isinstance(observed_license, dict):
        observed_license = observed_license.get("id")
    if observed_license is None:
        rights = metadata.get("rights")
        if isinstance(rights, list) and rights and isinstance(rights[0], dict):
            observed_license = rights[0].get("id")
    if (
        not isinstance(expected_license, str)
        or not isinstance(observed_license, str)
        or _normalized_license(observed_license)
        != _normalized_license(expected_license)
    ):
        raise ValueError("Zenodo license mismatch")

    expected_related = expected_metadata.get("related_identifiers")
    observed_related = metadata.get("related_identifiers")
    if not isinstance(expected_related, list) or not expected_related:
        raise ValueError("local Zenodo metadata has no related identifier")
    if not isinstance(observed_related, list):
        raise ValueError("Zenodo related identifiers are missing")
    expected_identities = {
        _related_identity(item)
        for item in expected_related
        if isinstance(item, dict)
    }
    observed_identities = {
        _related_identity(item)
        for item in observed_related
        if isinstance(item, dict)
    }
    if expected_identities != observed_identities:
        raise ValueError("Zenodo related identifier mismatch")


def request(url: str, token: str | None = None) -> Request:
    headers = {"User-Agent": "kn11-release-verifier/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return Request(url, headers=headers)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-id", required=True)
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=Path("dist/release"),
    )
    parser.add_argument("--base-url", default="https://zenodo.org")
    parser.add_argument(
        "--token-env",
        help="optional environment variable containing a draft-access token",
    )
    parser.add_argument(
        "--metadata-file",
        type=Path,
        default=Path(".zenodo.json"),
    )
    parser.add_argument(
        "--claim-file",
        type=Path,
        default=Path("research/claim.json"),
    )
    args = parser.parse_args()

    token = os.environ.get(args.token_env) if args.token_env else None
    metadata_url = (
        f"{args.base_url.rstrip('/')}/api/records/{args.record_id}"
    )
    with urlopen(request(metadata_url, token), timeout=60) as response:
        record = json.load(response)
    expected_metadata = json.loads(
        args.metadata_file.read_text(encoding="utf-8")
    )
    claim = json.loads(args.claim_file.read_text(encoding="utf-8"))
    verify_record_metadata(record, expected_metadata, claim, args.record_id)
    print(f"verified Zenodo metadata for record {args.record_id}")

    expected = local_inventory(args.release_dir)
    remote = remote_entries(record)
    if set(remote) != set(expected):
        raise SystemExit(
            "Zenodo filename set mismatch: "
            f"remote={sorted(remote)}, expected={sorted(expected)}"
        )
    for name in sorted(expected):
        expected_size, expected_sha256 = expected[name]
        remote_size, download_url = remote[name]
        if remote_size != expected_size:
            raise SystemExit(f"Zenodo byte-count mismatch: {name}")
        with urlopen(request(download_url, token), timeout=300) as response:
            observed_size, observed_sha256 = sha256_stream(response)
        if (
            observed_size != expected_size
            or observed_sha256 != expected_sha256
        ):
            raise SystemExit(f"Zenodo content mismatch: {name}")
        print(f"verified {name}")
    print(f"Zenodo record {args.record_id} matches all four release files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
