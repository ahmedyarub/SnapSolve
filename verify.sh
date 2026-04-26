#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "🔍 Starting Static Analysis & Verification Loop..."

# 1. Python: Ruff (Linter & Formatter)
echo "Running Python Checks (Ruff)..."
# Check for unused imports, variables, and linting errors
ruff check .
# Check formatting without modifying files (forces AI to run the fix command if it fails)
ruff format --check .

# 2. C++ & Java: Formatting
echo "Running C++ / Java Format Checks..."
# Fails if clang-format detects changes are needed
find . -regex '.*\.\(cpp\|hpp\|c\|h\|java\)' -exec clang-format --dry-run --Werror {} +

# 3. JetBrains Qodana (Headless PyCharm/IntelliJ Inspections)
echo "Running IDE Inspections (Qodana)..."
# Fails if any new problems are introduced beyond the baseline threshold
qodana scan --fail-threshold 0 --print-problems

# 4. SonarQube Scanner
echo "Running SonarQube Quality Gate..."
# Waits for the server to process and fails if the Quality Gate fails
sonar-scanner -Dsonar.qualitygate.wait=true

echo "✅ All static analysis passed successfully!"
