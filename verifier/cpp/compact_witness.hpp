#ifndef KNWIT003_COMPACT_WITNESS_HPP
#define KNWIT003_COMPACT_WITNESS_HPP

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include <gmpxx.h>

namespace knwit003 {

inline constexpr std::size_t kMaximumBytes = 128U * 1024U * 1024U;
inline constexpr std::size_t kMaximumBlocks = 128U;
inline constexpr std::size_t kMaximumDimension = 1024U;
inline constexpr std::size_t kMaximumRankSum = 10'000U;
inline constexpr std::size_t kMaximumRationals = 1'000'000U;
inline constexpr std::size_t kMaximumIntegerBits = 131'072U;
inline constexpr std::size_t kMaximumDenominatorsPerBlock = 1'000'000U;
inline constexpr std::size_t kMaximumUleb128Bytes = 16U;

class ParseError final : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};

struct BlockLayout {
    std::string name;
    std::size_t dimension;
};

using Matrix = std::vector<std::vector<mpq_class>>;

struct MatrixBlock {
    std::string name;
    std::size_t dimension;
    Matrix matrix;
};

struct WitnessReport {
    std::size_t size_bytes;
    std::size_t block_count;
    std::size_t rank_sum;
    std::size_t rational_count;
    std::size_t maximum_numerator_bits;
    std::size_t maximum_denominator_bits;
};

using BlockConsumer = std::function<void(MatrixBlock&&)>;

WitnessReport parse_compact_witness(
    std::span<const std::uint8_t> bytes,
    std::span<const BlockLayout> expected_blocks,
    const BlockConsumer& consumer = {});

WitnessReport parse_compact_witness_file(
    const std::filesystem::path& path,
    std::span<const BlockLayout> expected_blocks,
    const BlockConsumer& consumer = {});

Matrix reconstruct_block(const MatrixBlock& block);

}  // namespace knwit003

#endif
