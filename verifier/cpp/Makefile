CXX ?= c++

CPPFLAGS += -isystem /opt/homebrew/include
CXXFLAGS += -std=c++20 -O2 -Wall -Wextra -Wpedantic -Wconversion
CXXFLAGS += -Wsign-conversion -Wshadow -Werror
LDFLAGS += -L/opt/homebrew/lib -Wl,-rpath,/opt/homebrew/lib
LDLIBS += -lgmpxx -lgmp

BUILD_DIR := build
TARGET := $(BUILD_DIR)/test_compact_witness
SOURCES := compact_witness.cpp test_compact_witness.cpp

.PHONY: all test test-external clean

all: $(TARGET)

$(TARGET): $(SOURCES) compact_witness.hpp
	mkdir -p $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SOURCES) $(LDFLAGS) $(LDLIBS) -o $@

test: $(TARGET)
	./$(TARGET)

test-external: $(TARGET)
	./$(TARGET) ../../build/compact-witness-fixture.bin

clean:
	rm -rf $(BUILD_DIR)
