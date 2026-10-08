#!/bin/sh
# Unit tests for src/logic on a PC (Linux, macOS, or Windows with MSYS2/WSL):  sh run_tests.sh
cd "$(dirname "$0")" && g++ -std=c++17 -Wall -Wextra -I../../src test_logic.cpp -o test_logic && ./test_logic
