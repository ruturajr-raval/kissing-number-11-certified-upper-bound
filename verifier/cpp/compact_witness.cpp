#include "compact_witness.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <fcntl.h>
#include <limits>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>

namespace knwit003 {
namespace {

constexpr std::array<std::uint8_t, 8> kMagic = {
    0x4b, 0x4e, 0x57, 0x49, 0x54, 0x30, 0x30, 0x33,
};

std::string indexed_path(
    const std::string& prefix,
    const std::size_t index) {
    return prefix + "[" + std::to_string(index) + "]";
}

std::size_t bit_length(const mpz_class& value) {
    if (value == 0) {
        return 0;
    }
    return mpz_sizeinbase(value.get_mpz_t(), 2);
}

class FileDescriptor final {
  public:
    explicit FileDescriptor(const int descriptor) : descriptor_(descriptor) {}
    FileDescriptor(const FileDescriptor&) = delete;
    FileDescriptor& operator=(const FileDescriptor&) = delete;
    ~FileDescriptor() {
        if (descriptor_ >= 0) {
            static_cast<void>(::close(descriptor_));
        }
    }

    int get() const {
        return descriptor_;
    }

  private:
    int descriptor_;
};

bool same_file_identity(const struct stat& left, const struct stat& right) {
    if (left.st_dev != right.st_dev ||
        left.st_ino != right.st_ino ||
        left.st_size != right.st_size) {
        return false;
    }
#if defined(__APPLE__)
    return left.st_mtimespec.tv_sec == right.st_mtimespec.tv_sec &&
           left.st_mtimespec.tv_nsec == right.st_mtimespec.tv_nsec &&
           left.st_ctimespec.tv_sec == right.st_ctimespec.tv_sec &&
           left.st_ctimespec.tv_nsec == right.st_ctimespec.tv_nsec;
#else
    return left.st_mtim.tv_sec == right.st_mtim.tv_sec &&
           left.st_mtim.tv_nsec == right.st_mtim.tv_nsec &&
           left.st_ctim.tv_sec == right.st_ctim.tv_sec &&
           left.st_ctim.tv_nsec == right.st_ctim.tv_nsec;
#endif
}

class Reader final {
  public:
    explicit Reader(const std::span<const std::uint8_t> bytes) : bytes_(bytes) {
        if (bytes_.size() > kMaximumBytes) {
            throw ParseError("witness exceeds byte limit");
        }
    }

    std::span<const std::uint8_t> read_exact(
        const std::size_t count,
        const std::string& path) {
        if (count > bytes_.size() - position_) {
            throw ParseError(path + ": truncated witness");
        }
        const auto result = bytes_.subspan(position_, count);
        position_ += count;
        return result;
    }

    std::uint8_t read_u8(const std::string& path) {
        return read_exact(1, path)[0];
    }

    std::uint16_t read_u16(const std::string& path) {
        const auto data = read_exact(2, path);
        return static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(data[0]) |
            static_cast<std::uint16_t>(
                static_cast<std::uint16_t>(data[1]) << 8U));
    }

    std::uint32_t read_u32(const std::string& path) {
        const auto data = read_exact(4, path);
        return static_cast<std::uint32_t>(
            static_cast<std::uint32_t>(data[0]) |
            (static_cast<std::uint32_t>(data[1]) << 8U) |
            (static_cast<std::uint32_t>(data[2]) << 16U) |
            (static_cast<std::uint32_t>(data[3]) << 24U));
    }

    mpz_class read_uleb128(const std::string& path) {
        mpz_class value = 0;
        unsigned long shift = 0;
        for (std::size_t index = 0; index < kMaximumUleb128Bytes; ++index) {
            const std::uint8_t byte = read_u8(path);
            const std::uint8_t payload =
                static_cast<std::uint8_t>(byte & 0x7fU);
            value += mpz_class(payload) << shift;
            if ((byte & 0x80U) == 0U) {
                if (index > 0U && payload == 0U) {
                    throw ParseError(path + ": noncanonical ULEB128");
                }
                return value;
            }
            shift += 7U;
        }
        throw ParseError(path + ": ULEB128 is too long");
    }

    std::size_t read_bounded_uleb128(
        const std::string& path,
        const std::size_t maximum) {
        const mpz_class value = read_uleb128(path);
        if (value > maximum) {
            throw ParseError(path + ": value exceeds limit");
        }
        return value.get_ui();
    }

    mpz_class read_magnitude(const std::string& path) {
        constexpr std::size_t maximum_bytes =
            (kMaximumIntegerBits + 7U) / 8U;
        const std::size_t length =
            read_bounded_uleb128(path + ".length", maximum_bytes);
        if (length == 0U) {
            throw ParseError(path + ": empty nonzero magnitude");
        }
        const auto data = read_exact(length, path);
        if (data.front() == 0U) {
            throw ParseError(path + ": magnitude has a leading zero");
        }

        mpz_class value = 0;
        mpz_import(
            value.get_mpz_t(),
            data.size(),
            1,
            1,
            1,
            0,
            data.data());
        if (bit_length(value) > kMaximumIntegerBits) {
            throw ParseError(path + ": integer exceeds bit limit");
        }
        return value;
    }

    mpz_class read_signed_integer(const std::string& path) {
        const std::uint8_t sign = read_u8(path + ".sign");
        if (sign == 0U) {
            return 0;
        }
        if (sign != 1U && sign != 2U) {
            throw ParseError(path + ": invalid integer sign");
        }
        mpz_class value = read_magnitude(path + ".magnitude");
        if (sign == 2U) {
            value = -value;
        }
        return value;
    }

    bool at_end() const {
        return position_ == bytes_.size();
    }

  private:
    std::span<const std::uint8_t> bytes_;
    std::size_t position_ = 0;
};

std::size_t expected_value_count(const std::size_t dimension) {
    return dimension * (dimension + 1U) / 2U;
}

struct ParsedBlock {
    MatrixBlock block;
    std::size_t value_count;
    std::size_t maximum_numerator_bits;
    std::size_t maximum_denominator_bits;
};

ParsedBlock read_block(
    Reader& reader,
    const BlockLayout& layout,
    const std::size_t block_index,
    const std::size_t remaining_rank_budget,
    const std::size_t remaining_rational_budget) {
    const std::string path = indexed_path("block", block_index);
    const std::size_t dimension = reader.read_u16(path + ".dimension");

    if (dimension != layout.dimension) {
        std::ostringstream message;
        message << path << ": expected dimension " << layout.dimension
                << ", received " << dimension;
        throw ParseError(message.str());
    }
    if (dimension == 0U || dimension > kMaximumDimension) {
        throw ParseError(path + ": invalid dimension");
    }
    if (dimension > remaining_rank_budget) {
        throw ParseError("rank-sum limit exceeded");
    }

    const std::size_t value_count = expected_value_count(dimension);
    if (value_count > remaining_rational_budget) {
        throw ParseError("rational-count limit exceeded");
    }

    const std::size_t denominator_count =
        reader.read_u32(path + ".denominator_count");
    if (denominator_count == 0U) {
        throw ParseError(path + ": matrix block lacks denominators");
    }
    if (denominator_count > kMaximumDenominatorsPerBlock) {
        throw ParseError(path + ": too many denominators");
    }
    if (denominator_count > value_count) {
        throw ParseError(path + ": denominator table contains unused values");
    }

    std::vector<mpz_class> denominators;
    denominators.reserve(denominator_count);
    mpz_class previous = 0;
    for (std::size_t index = 0; index < denominator_count; ++index) {
        const mpz_class value =
            reader.read_magnitude(indexed_path(path + ".denominators", index));
        if (value <= previous) {
            throw ParseError(
                path +
                ": denominators must be unique and strictly increasing");
        }
        denominators.push_back(value);
        previous = value;
    }

    std::vector<mpq_class> values;
    values.reserve(value_count);
    std::vector<bool> used_denominators(denominator_count, false);
    std::size_t maximum_numerator_bits = 0;
    std::size_t maximum_denominator_bits = 0;
    for (std::size_t index = 0; index < value_count; ++index) {
        const std::string value_path = indexed_path(path + ".values", index);
        const std::size_t denominator_index = reader.read_bounded_uleb128(
            value_path + ".denominator_index",
            denominator_count);
        if (denominator_index >= denominator_count) {
            throw ParseError(
                value_path + ": denominator index is out of range");
        }
        const mpz_class numerator =
            reader.read_signed_integer(value_path + ".numerator");
        const mpz_class& denominator = denominators[denominator_index];

        const mpz_class numerator_magnitude =
            numerator < 0 ? -numerator : numerator;
        mpz_class divisor = 0;
        mpz_gcd(
            divisor.get_mpz_t(),
            numerator_magnitude.get_mpz_t(),
            denominator.get_mpz_t());
        if (divisor != 1) {
            throw ParseError(value_path + ": rational is not reduced");
        }

        mpq_class value(numerator, denominator);
        value.canonicalize();
        values.push_back(std::move(value));
        used_denominators[denominator_index] = true;
        maximum_numerator_bits =
            std::max(maximum_numerator_bits, bit_length(numerator_magnitude));
        maximum_denominator_bits =
            std::max(maximum_denominator_bits, bit_length(denominator));
    }
    if (std::find(
            used_denominators.begin(),
            used_denominators.end(),
            false) != used_denominators.end()) {
        throw ParseError(path + ": denominator table contains unused values");
    }

    Matrix matrix(
        dimension,
        std::vector<mpq_class>(dimension, mpq_class(0)));
    std::size_t position = 0;
    for (std::size_t row = 0; row < dimension; ++row) {
        for (std::size_t column = row; column < dimension; ++column) {
            matrix[row][column] = values[position];
            matrix[column][row] = values[position];
            ++position;
        }
    }
    if (position != values.size()) {
        throw ParseError(path + ": internal value-count mismatch");
    }

    return ParsedBlock{
        MatrixBlock{
            layout.name,
            dimension,
            std::move(matrix),
        },
        value_count,
        maximum_numerator_bits,
        maximum_denominator_bits,
    };
}

}  // namespace

WitnessReport parse_compact_witness(
    const std::span<const std::uint8_t> bytes,
    const std::span<const BlockLayout> expected_blocks,
    const BlockConsumer& consumer) {
    if (expected_blocks.size() > kMaximumBlocks) {
        throw ParseError("expected block layout exceeds block limit");
    }

    Reader reader(bytes);
    const auto magic = reader.read_exact(kMagic.size(), "magic");
    if (!std::equal(magic.begin(), magic.end(), kMagic.begin())) {
        throw ParseError("incorrect witness magic");
    }

    const std::size_t block_count = reader.read_u32("block_count");
    if (block_count > kMaximumBlocks) {
        throw ParseError("block-count limit exceeded");
    }
    if (block_count != expected_blocks.size()) {
        std::ostringstream message;
        message << "expected " << expected_blocks.size()
                << " blocks, received " << block_count;
        throw ParseError(message.str());
    }

    std::size_t rank_sum = 0;
    std::size_t rational_count = 0;
    std::size_t maximum_numerator_bits = 0;
    std::size_t maximum_denominator_bits = 0;
    for (std::size_t block_index = 0;
         block_index < expected_blocks.size();
         ++block_index) {
        ParsedBlock parsed = read_block(
            reader,
            expected_blocks[block_index],
            block_index,
            kMaximumRankSum - rank_sum,
            kMaximumRationals - rational_count);
        rank_sum += parsed.block.dimension;
        rational_count += parsed.value_count;
        maximum_numerator_bits =
            std::max(maximum_numerator_bits, parsed.maximum_numerator_bits);
        maximum_denominator_bits =
            std::max(maximum_denominator_bits, parsed.maximum_denominator_bits);
        if (consumer) {
            consumer(std::move(parsed.block));
        }
    }

    if (!reader.at_end()) {
        throw ParseError("witness has trailing bytes");
    }
    return WitnessReport{
        bytes.size(),
        block_count,
        rank_sum,
        rational_count,
        maximum_numerator_bits,
        maximum_denominator_bits,
    };
}

WitnessReport parse_compact_witness_file(
    const std::filesystem::path& path,
    const std::span<const BlockLayout> expected_blocks,
    const BlockConsumer& consumer) {
    int flags = O_RDONLY;
#if defined(O_CLOEXEC)
    flags |= O_CLOEXEC;
#endif
#if defined(O_NOFOLLOW)
    flags |= O_NOFOLLOW;
#endif
    const int raw_descriptor = ::open(path.c_str(), flags);
    if (raw_descriptor < 0) {
        throw ParseError("cannot open witness");
    }
    const FileDescriptor descriptor(raw_descriptor);

    struct stat before {};
    if (::fstat(descriptor.get(), &before) != 0) {
        throw ParseError("cannot determine witness metadata");
    }
    if (!S_ISREG(before.st_mode)) {
        throw ParseError("witness is not a regular file");
    }
    if (before.st_size < 0) {
        throw ParseError("witness size is invalid");
    }
    const auto file_size = static_cast<std::uintmax_t>(before.st_size);
    if (file_size > kMaximumBytes) {
        throw ParseError("witness exceeds byte limit");
    }
    if (file_size > std::numeric_limits<std::size_t>::max()) {
        throw ParseError("witness size is not addressable");
    }

    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(file_size));
    std::size_t position = 0;
    while (position < bytes.size()) {
        const ssize_t count = ::read(
            descriptor.get(),
            bytes.data() + position,
            bytes.size() - position);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            throw ParseError("witness changed while reading");
        }
        position += static_cast<std::size_t>(count);
    }
    std::uint8_t trailing = 0;
    ssize_t trailing_count = 0;
    do {
        trailing_count = ::read(descriptor.get(), &trailing, 1);
    } while (trailing_count < 0 && errno == EINTR);
    if (trailing_count != 0) {
        throw ParseError("witness changed while reading");
    }

    struct stat after {};
    if (::fstat(descriptor.get(), &after) != 0 ||
        !same_file_identity(before, after)) {
        throw ParseError("witness changed while reading");
    }
    return parse_compact_witness(bytes, expected_blocks, consumer);
}

Matrix reconstruct_block(const MatrixBlock& block) {
    if (block.dimension == 0U || block.dimension > kMaximumDimension) {
        throw ParseError("block has invalid reconstruction dimension");
    }
    if (block.matrix.size() != block.dimension) {
        throw ParseError("block has inconsistent matrix dimensions");
    }
    for (std::size_t row = 0; row < block.dimension; ++row) {
        if (block.matrix[row].size() != block.dimension) {
            throw ParseError("block has inconsistent matrix dimensions");
        }
        for (std::size_t column = row + 1U;
             column < block.dimension;
             ++column) {
            if (block.matrix[row][column] != block.matrix[column][row]) {
                throw ParseError("block matrix is not symmetric");
            }
        }
    }
    return block.matrix;
}

}  // namespace knwit003
