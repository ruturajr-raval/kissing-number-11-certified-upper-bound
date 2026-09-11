"""Round-trip and tamper tests for the compact witness parser."""

from __future__ import annotations

import tempfile
import unittest
import sys
from fractions import Fraction
from pathlib import Path

TEST_DIRECTORY = Path(__file__).resolve().parent
VERIFIER_DIRECTORY = TEST_DIRECTORY.parent
sys.path.insert(0, str(VERIFIER_DIRECTORY))

from compact_witness import (
    BlockLayout,
    CompactWitnessError,
    WitnessLimits,
    read_compact_witness,
    read_compact_witness_bytes,
    reconstruct_block,
)


MAGIC = b"KNWIT003"


def uleb128(value: int) -> bytes:
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


def magnitude(value: int) -> bytes:
    data = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    return uleb128(len(data)) + data


def signed(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    return bytes([1 if value > 0 else 2]) + magnitude(abs(value))


def fixture_bytes() -> bytes:
    output = bytearray(MAGIC)
    output += (2).to_bytes(4, "little")

    output += (2).to_bytes(2, "little")
    output += (2).to_bytes(4, "little")
    output += magnitude(1)
    output += magnitude(2)
    for denominator_index, numerator in ((0, 2), (0, -2), (1, 7)):
        output += uleb128(denominator_index)
        output += signed(numerator)

    output += (1).to_bytes(2, "little")
    output += (1).to_bytes(4, "little")
    output += magnitude(1)
    output += uleb128(0)
    output += signed(0)
    return bytes(output)


class CompactWitnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "witness.bin"
        self.path.write_bytes(fixture_bytes())
        self.layout = (BlockLayout("F/00", 2), BlockLayout("a/00", 1))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_fixture(self) -> None:
        blocks = []
        report = read_compact_witness(
            self.path, self.layout, consumer=blocks.append
        )
        self.assertEqual(report.block_count, 2)
        self.assertEqual(report.rank_sum, 3)
        self.assertEqual(report.rational_count, 4)
        self.assertEqual(
            reconstruct_block(blocks[0]),
            (
                (Fraction(2), Fraction(-2)),
                (Fraction(-2), Fraction(7, 2)),
            ),
        )
        self.assertEqual(reconstruct_block(blocks[1]), ((Fraction(0),),))

    def test_immutable_byte_parser_matches_path_parser(self) -> None:
        path_report = read_compact_witness(self.path, self.layout)
        byte_report = read_compact_witness_bytes(
            self.path.read_bytes(),
            self.layout,
        )
        self.assertEqual(path_report, byte_report)

    def test_rejects_symlink_path(self) -> None:
        link = self.path.with_name("witness-link.bin")
        link.symlink_to(self.path.name)
        with self.assertRaisesRegex(CompactWitnessError, "cannot open witness"):
            read_compact_witness(link, self.layout)

    def test_rejects_rational_budget_before_block_allocation(self) -> None:
        with self.assertRaisesRegex(
            CompactWitnessError,
            "rational-count limit exceeded",
        ):
            read_compact_witness(
                self.path,
                self.layout,
                limits=WitnessLimits(max_rationals=2),
            )

    def test_rejects_trailing_bytes(self) -> None:
        self.path.write_bytes(fixture_bytes() + b"\x00")
        with self.assertRaisesRegex(CompactWitnessError, "trailing bytes"):
            read_compact_witness(self.path, self.layout)

    def test_rejects_noncanonical_uleb128(self) -> None:
        data = fixture_bytes()
        first_denominator_length = len(MAGIC) + 4 + 2 + 4
        tampered = (
            data[:first_denominator_length]
            + b"\x81\x00"
            + data[first_denominator_length + 1 :]
        )
        self.path.write_bytes(tampered)
        with self.assertRaisesRegex(CompactWitnessError, "noncanonical ULEB128"):
            read_compact_witness(self.path, self.layout)

    def test_rejects_unreduced_rational(self) -> None:
        data = bytearray(fixture_bytes())
        data[33] = 6
        self.path.write_bytes(data)
        with self.assertRaisesRegex(CompactWitnessError, "rational is not reduced"):
            read_compact_witness(self.path, self.layout)

    def test_rejects_unused_denominator(self) -> None:
        data = bytearray(fixture_bytes())
        data[30] = 0
        self.path.write_bytes(data)
        with self.assertRaisesRegex(CompactWitnessError, "unused values"):
            read_compact_witness(self.path, self.layout)


if __name__ == "__main__":
    unittest.main()
