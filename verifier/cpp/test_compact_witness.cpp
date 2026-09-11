#include "compact_witness.hpp"

#include <array>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <iostream>
#include <span>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr std::array<std::uint8_t, 44> kCanonicalFixture = {
    0x4b, 0x4e, 0x57, 0x49, 0x54, 0x30, 0x30, 0x33,
    0x02, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x02, 0x00, 0x00, 0x00,
    0x01, 0x01, 0x01, 0x02,
    0x00, 0x01, 0x01, 0x02,
    0x00, 0x02, 0x01, 0x02,
    0x01, 0x01, 0x01, 0x07,
    0x01, 0x00, 0x01, 0x00, 0x00, 0x00,
    0x01, 0x01, 0x00, 0x00,
};

const std::array<knwit003::BlockLayout, 2> kLayout = {
    knwit003::BlockLayout{"F/00", 2},
    knwit003::BlockLayout{"a/00", 1},
};

void require(const bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

std::vector<knwit003::MatrixBlock> parse_blocks(
    const std::span<const std::uint8_t> bytes,
    knwit003::WitnessReport* report = nullptr) {
    std::vector<knwit003::MatrixBlock> blocks;
    const knwit003::WitnessReport parsed = knwit003::parse_compact_witness(
        bytes,
        kLayout,
        [&blocks](knwit003::MatrixBlock&& block) {
            blocks.push_back(std::move(block));
        });
    if (report != nullptr) {
        *report = parsed;
    }
    return blocks;
}

void expect_parse_error(
    const std::vector<std::uint8_t>& bytes,
    const std::string& expected_text) {
    try {
        static_cast<void>(parse_blocks(bytes));
    } catch (const knwit003::ParseError& error) {
        require(
            std::string(error.what()).find(expected_text) != std::string::npos,
            "unexpected parser error: " + std::string(error.what()));
        return;
    }
    throw std::runtime_error("malformed witness was accepted");
}

void test_canonical_fixture() {
    knwit003::WitnessReport report{};
    const auto blocks = parse_blocks(kCanonicalFixture, &report);
    require(report.size_bytes == 44, "incorrect fixture byte count");
    require(report.block_count == 2, "incorrect block count");
    require(report.rank_sum == 3, "incorrect rank sum");
    require(report.rational_count == 4, "incorrect rational count");
    require(report.maximum_numerator_bits == 3, "incorrect numerator bit count");
    require(
        report.maximum_denominator_bits == 2,
        "incorrect denominator bit count");
    require(blocks.size() == 2, "consumer received incorrect block count");

    const knwit003::Matrix first = knwit003::reconstruct_block(blocks[0]);
    const knwit003::Matrix expected_first = {
        {mpq_class(2), mpq_class(-2)},
        {mpq_class(-2), mpq_class(7, 2)},
    };
    require(first == expected_first, "first exact matrix is incorrect");

    const knwit003::Matrix second = knwit003::reconstruct_block(blocks[1]);
    const knwit003::Matrix expected_second = {{mpq_class(0)}};
    require(second == expected_second, "zero exact matrix is incorrect");
}

void test_rejections() {
    std::vector<std::uint8_t> trailing(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    trailing.push_back(0);
    expect_parse_error(trailing, "trailing bytes");

    std::vector<std::uint8_t> noncanonical(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    noncanonical.erase(noncanonical.begin() + 18);
    noncanonical.insert(noncanonical.begin() + 18, {0x81, 0x00});
    expect_parse_error(noncanonical, "noncanonical ULEB128");

    std::vector<std::uint8_t> leading_zero(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    leading_zero.erase(leading_zero.begin() + 18, leading_zero.begin() + 20);
    leading_zero.insert(leading_zero.begin() + 18, {0x02, 0x00, 0x01});
    expect_parse_error(leading_zero, "leading zero");

    std::vector<std::uint8_t> unordered_denominators(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    unordered_denominators[21] = 1;
    expect_parse_error(unordered_denominators, "strictly increasing");

    std::vector<std::uint8_t> invalid_sign(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    invalid_sign[23] = 3;
    expect_parse_error(invalid_sign, "invalid integer sign");

    std::vector<std::uint8_t> unreduced(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    unreduced[33] = 6;
    expect_parse_error(unreduced, "rational is not reduced");

    std::vector<std::uint8_t> unused_denominator(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    unused_denominator[30] = 0;
    expect_parse_error(unused_denominator, "unused values");

    std::vector<std::uint8_t> denominator_out_of_range(
        kCanonicalFixture.begin(),
        kCanonicalFixture.end());
    denominator_out_of_range[30] = 2;
    expect_parse_error(denominator_out_of_range, "out of range");
}

}  // namespace

void test_external_fixture(const std::filesystem::path& path) {
    std::vector<knwit003::MatrixBlock> blocks;
    const knwit003::WitnessReport report =
        knwit003::parse_compact_witness_file(
            path,
            kLayout,
            [&blocks](knwit003::MatrixBlock&& block) {
                blocks.push_back(std::move(block));
            });
    require(report.size_bytes == kCanonicalFixture.size(), "external fixture size");
    require(blocks.size() == 2, "external fixture block count");
    require(
        knwit003::reconstruct_block(blocks[0]) ==
            knwit003::Matrix{
                {mpq_class(2), mpq_class(-2)},
                {mpq_class(-2), mpq_class(7, 2)},
            },
        "external fixture first matrix");
}

int main(const int argument_count, char** arguments) {
    try {
        test_canonical_fixture();
        test_rejections();
        if (argument_count == 2) {
            test_external_fixture(arguments[1]);
        } else if (argument_count != 1) {
            throw std::runtime_error("usage: test_compact_witness [fixture]");
        }
        std::cout << "KNWIT003 C++ parser tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "KNWIT003 C++ parser test failed: " << error.what() << '\n';
        return 1;
    }
}
