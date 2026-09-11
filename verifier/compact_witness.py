#!/usr/bin/env python3
"""Canonical parser for compact exact rational matrix witness files."""

from __future__ import annotations

import hashlib
import io
import math
import os
import stat
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO, Callable, Iterable, Sequence


MAGIC = b"KNWIT003"


class CompactWitnessError(Exception):
    """Raised when compact witness bytes are malformed or noncanonical."""


@dataclass(frozen=True)
class WitnessLimits:
    max_bytes: int = 128 * 1024 * 1024
    max_blocks: int = 128
    max_dimension: int = 1024
    max_rank_sum: int = 10_000
    max_rationals: int = 1_000_000
    max_integer_bits: int = 131_072
    max_denominators_per_block: int = 1_000_000


DEFAULT_LIMITS = WitnessLimits()


@dataclass(frozen=True)
class BlockLayout:
    name: str
    dimension: int


@dataclass(frozen=True)
class LDLBlock:
    name: str
    dimension: int
    rank: int
    permutation: tuple[int, ...]
    diagonal: tuple[Fraction, ...]
    columns: tuple[tuple[Fraction, ...], ...]


@dataclass(frozen=True)
class MatrixBlock:
    name: str
    dimension: int
    matrix: tuple[tuple[Fraction, ...], ...]

    @property
    def rank(self) -> int:
        """Strict positivity verification certifies full rank."""

        return self.dimension


@dataclass(frozen=True)
class WitnessReport:
    sha256: str
    size_bytes: int
    block_count: int
    rank_sum: int
    rational_count: int
    maximum_numerator_bits: int
    maximum_denominator_bits: int


class _Reader:
    def __init__(self, stream: BinaryIO, limits: WitnessLimits) -> None:
        self.stream = stream
        self.limits = limits
        self.bytes_read = 0

    def read_exact(self, count: int, path: str) -> bytes:
        if count < 0:
            raise CompactWitnessError(f"{path}: negative read length")
        data = self.stream.read(count)
        self.bytes_read += len(data)
        if len(data) != count:
            raise CompactWitnessError(f"{path}: truncated witness")
        if self.bytes_read > self.limits.max_bytes:
            raise CompactWitnessError("witness exceeds byte limit")
        return data

    def read_u8(self, path: str) -> int:
        return self.read_exact(1, path)[0]

    def read_u16(self, path: str) -> int:
        return int.from_bytes(self.read_exact(2, path), "little")

    def read_u32(self, path: str) -> int:
        return int.from_bytes(self.read_exact(4, path), "little")

    def read_uleb128(self, path: str) -> int:
        value = 0
        shift = 0
        encoded = bytearray()
        while True:
            if len(encoded) >= 16:
                raise CompactWitnessError(f"{path}: ULEB128 is too long")
            byte = self.read_u8(path)
            encoded.append(byte)
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                break
            shift += 7
        canonical = bytearray()
        remaining = value
        while True:
            byte = remaining & 0x7F
            remaining >>= 7
            canonical.append(byte | (0x80 if remaining else 0))
            if not remaining:
                break
        if encoded != canonical:
            raise CompactWitnessError(f"{path}: noncanonical ULEB128")
        return value

    def read_magnitude(self, path: str) -> int:
        length = self.read_uleb128(f"{path}.length")
        if length == 0:
            raise CompactWitnessError(f"{path}: empty nonzero magnitude")
        max_bytes = (self.limits.max_integer_bits + 7) // 8
        if length > max_bytes:
            raise CompactWitnessError(f"{path}: integer exceeds bit limit")
        data = self.read_exact(length, path)
        if data[0] == 0:
            raise CompactWitnessError(f"{path}: magnitude has a leading zero")
        value = int.from_bytes(data, "big")
        if value.bit_length() > self.limits.max_integer_bits:
            raise CompactWitnessError(f"{path}: integer exceeds bit limit")
        return value

    def read_signed_integer(self, path: str) -> int:
        sign = self.read_u8(f"{path}.sign")
        if sign == 0:
            return 0
        if sign not in (1, 2):
            raise CompactWitnessError(f"{path}: invalid integer sign")
        value = self.read_magnitude(f"{path}.magnitude")
        return value if sign == 1 else -value


def _stable_regular_file(path: Path, limits: WitnessLimits) -> tuple[BinaryIO, os.stat_result]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise CompactWitnessError(f"cannot open witness: {exc}") from exc
    if not stat.S_ISREG(before.st_mode):
        os.close(descriptor)
        raise CompactWitnessError("witness is not a regular file")
    if before.st_size > limits.max_bytes:
        os.close(descriptor)
        raise CompactWitnessError("witness exceeds byte limit")
    stream = os.fdopen(descriptor, "rb", closefd=True)
    return stream, before


def _expected_value_count(dimension: int) -> int:
    return dimension * (dimension + 1) // 2


def _read_block(
    reader: _Reader,
    layout: BlockLayout,
    block_index: int,
    limits: WitnessLimits,
    remaining_rank: int,
    remaining_rationals: int,
) -> tuple[MatrixBlock, int, int, int]:
    path = f"block[{block_index}]"
    dimension = reader.read_u16(f"{path}.dimension")
    if dimension != layout.dimension:
        raise CompactWitnessError(
            f"{path}: expected dimension {layout.dimension}, received {dimension}"
        )
    if dimension < 1 or dimension > limits.max_dimension:
        raise CompactWitnessError(f"{path}: invalid dimension")
    if dimension > remaining_rank:
        raise CompactWitnessError("rank-sum limit exceeded")
    value_count = _expected_value_count(dimension)
    if value_count > remaining_rationals:
        raise CompactWitnessError("rational-count limit exceeded")

    denominator_count = reader.read_u32(f"{path}.denominator_count")
    if denominator_count > limits.max_denominators_per_block:
        raise CompactWitnessError(f"{path}: too many denominators")
    if denominator_count == 0:
        raise CompactWitnessError(f"{path}: matrix block lacks denominators")
    if denominator_count > value_count:
        raise CompactWitnessError(f"{path}: denominator table contains unused values")

    denominators: list[int] = []
    previous = 0
    for index in range(denominator_count):
        value = reader.read_magnitude(f"{path}.denominators[{index}]")
        if value <= previous:
            raise CompactWitnessError(
                f"{path}: denominators must be unique and strictly increasing"
            )
        denominators.append(value)
        previous = value

    values: list[Fraction] = []
    used_denominators: set[int] = set()
    maximum_numerator_bits = 0
    maximum_denominator_bits = 0
    for index in range(value_count):
        denominator_index = reader.read_uleb128(
            f"{path}.values[{index}].denominator_index"
        )
        if denominator_index >= len(denominators):
            raise CompactWitnessError(
                f"{path}.values[{index}]: denominator index is out of range"
            )
        numerator = reader.read_signed_integer(
            f"{path}.values[{index}].numerator"
        )
        denominator = denominators[denominator_index]
        if math.gcd(abs(numerator), denominator) != 1:
            raise CompactWitnessError(
                f"{path}.values[{index}]: rational is not reduced"
            )
        values.append(Fraction(numerator, denominator))
        used_denominators.add(denominator_index)
        maximum_numerator_bits = max(
            maximum_numerator_bits, abs(numerator).bit_length()
        )
        maximum_denominator_bits = max(
            maximum_denominator_bits, denominator.bit_length()
        )
    if used_denominators != set(range(len(denominators))):
        raise CompactWitnessError(f"{path}: denominator table contains unused values")

    matrix = [
        [Fraction(0) for _ in range(dimension)]
        for _ in range(dimension)
    ]
    position = 0
    for row in range(dimension):
        for column in range(row, dimension):
            value = values[position]
            position += 1
            matrix[row][column] = value
            matrix[column][row] = value
    if position != len(values):
        raise CompactWitnessError(f"{path}: internal value-count mismatch")
    return (
        MatrixBlock(
            name=layout.name,
            dimension=dimension,
            matrix=tuple(tuple(row) for row in matrix),
        ),
        value_count,
        maximum_numerator_bits,
        maximum_denominator_bits,
    )


def _read_compact_witness_stream(
    stream: BinaryIO,
    size_bytes: int,
    expected_blocks: Sequence[BlockLayout],
    *,
    consumer: Callable[[MatrixBlock], None] | None = None,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> WitnessReport:
    if len(expected_blocks) > limits.max_blocks:
        raise CompactWitnessError("expected block layout exceeds block limit")
    if size_bytes > limits.max_bytes:
        raise CompactWitnessError("witness exceeds byte limit")
    digest = hashlib.sha256()

    class HashingStream:
        def read(self, count: int = -1) -> bytes:
            data = stream.read(count)
            digest.update(data)
            return data

    hashing_stream = HashingStream()
    reader = _Reader(hashing_stream, limits)
    rank_sum = 0
    rational_count = 0
    maximum_numerator_bits = 0
    maximum_denominator_bits = 0
    try:
        if reader.read_exact(len(MAGIC), "magic") != MAGIC:
            raise CompactWitnessError("incorrect witness magic")
        block_count = reader.read_u32("block_count")
        if block_count != len(expected_blocks):
            raise CompactWitnessError(
                f"expected {len(expected_blocks)} blocks, received {block_count}"
            )
        for block_index, layout in enumerate(expected_blocks):
            block, count, numerator_bits, denominator_bits = _read_block(
                reader,
                layout,
                block_index,
                limits,
                limits.max_rank_sum - rank_sum,
                limits.max_rationals - rational_count,
            )
            rank_sum += block.dimension
            rational_count += count
            maximum_numerator_bits = max(maximum_numerator_bits, numerator_bits)
            maximum_denominator_bits = max(
                maximum_denominator_bits, denominator_bits
            )
            if consumer is not None:
                consumer(block)
        if hashing_stream.read(1):
            raise CompactWitnessError("witness has trailing bytes")
    except OSError as exc:
        raise CompactWitnessError(f"cannot read witness: {exc}") from exc
    if reader.bytes_read != size_bytes:
        raise CompactWitnessError("witness size changed while reading")
    return WitnessReport(
        sha256=digest.hexdigest(),
        size_bytes=size_bytes,
        block_count=len(expected_blocks),
        rank_sum=rank_sum,
        rational_count=rational_count,
        maximum_numerator_bits=maximum_numerator_bits,
        maximum_denominator_bits=maximum_denominator_bits,
    )


def read_compact_witness_bytes(
    data: bytes,
    expected_blocks: Sequence[BlockLayout],
    *,
    consumer: Callable[[MatrixBlock], None] | None = None,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> WitnessReport:
    """Parse one immutable witness byte string."""

    if not isinstance(data, bytes):
        raise CompactWitnessError("witness data must be immutable bytes")
    return _read_compact_witness_stream(
        io.BytesIO(data),
        len(data),
        expected_blocks,
        consumer=consumer,
        limits=limits,
    )


def read_compact_witness(
    path: str | os.PathLike[str],
    expected_blocks: Sequence[BlockLayout],
    *,
    consumer: Callable[[MatrixBlock], None] | None = None,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> WitnessReport:
    """Parse a strict witness and optionally stream each block to a consumer."""

    witness_path = Path(path)
    stream, before = _stable_regular_file(witness_path, limits)
    try:
        report = _read_compact_witness_stream(
            stream,
            before.st_size,
            expected_blocks,
            consumer=consumer,
            limits=limits,
        )
        after = os.fstat(stream.fileno())
    finally:
        stream.close()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise CompactWitnessError("witness changed while reading")
    return report


def reconstruct_block(
    block: LDLBlock | MatrixBlock,
) -> tuple[tuple[Fraction, ...], ...]:
    """Reconstruct one original-coordinate matrix for tests and reference use."""

    if isinstance(block, MatrixBlock):
        if len(block.matrix) != block.dimension or any(
            len(row) != block.dimension for row in block.matrix
        ):
            raise CompactWitnessError(
                f"{block.name}: matrix dimensions are inconsistent"
            )
        if any(
            block.matrix[row][column] != block.matrix[column][row]
            for row in range(block.dimension)
            for column in range(row + 1, block.dimension)
        ):
            raise CompactWitnessError(f"{block.name}: matrix is not symmetric")
        return block.matrix

    permuted = [
        [Fraction(0) for _ in range(block.dimension)]
        for _ in range(block.dimension)
    ]
    for diagonal, column in zip(block.diagonal, block.columns):
        for row, left in enumerate(column):
            if not left:
                continue
            for other, right in enumerate(column):
                if right:
                    permuted[row][other] += diagonal * left * right
    result = [
        [Fraction(0) for _ in range(block.dimension)]
        for _ in range(block.dimension)
    ]
    for row, original_row in enumerate(block.permutation):
        for column, original_column in enumerate(block.permutation):
            result[original_row][original_column] = permuted[row][column]
    return tuple(tuple(row) for row in result)
