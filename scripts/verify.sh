#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "🔍 Starting Static Analysis & Verification Loop..."

# 1. Python: Ruff (Linter & Formatter)
echo "Running Python Checks (Ruff)..."
# Check for unused imports, variables, and linting errors
ruff check .
RUFF_CHECK_EXIT_CODE=$?
if [ "$RUFF_CHECK_EXIT_CODE" -ne 0 ]; then
    echo -e "\e[31mRuff check failed. Fix the issues listed above.\e[0m"
    exit 1
fi

# Check formatting without modifying files (forces AI to run the fix command if it fails)
ruff format --check .
RUFF_FORMAT_EXIT_CODE=$?
if [ "$RUFF_FORMAT_EXIT_CODE" -ne 0 ]; then
    echo -e "\e[31mRuff format check failed. Run 'ruff format .' to fix formatting issues.\e[0m"
    exit 1
fi

# 2. JetBrains Qodana (Headless PyCharm/IntelliJ Inspections)
echo "Running IDE Inspections (Qodana)..."
# Fails if any new problems are introduced beyond the baseline threshold
export NONINTERACTIVE=true
qodana scan --fail-threshold 0 --print-problems --apply-fixes
QODANA_EXIT_CODE=$?
if [ "$QODANA_EXIT_CODE" -ne 0 ]; then
    echo -e "\e[31mQodana inspection failed. Fix the issues listed above.\e[0m"
    exit 1
fi

# 3. SonarQube Scanner
echo "Running SonarQube Quality Gate..."

# 1. Run the scanner
sonar-scanner -Dsonar.qualitygate.wait=true -Dsonar.python.version=3
SONAR_EXIT_CODE=$?

# 2. Fetch the issues directly from the SonarQube API
SONAR_URL="http://localhost:9000"
PROJECT_KEY="SnapSolve"          # Update this to your exact sonar.projectKey

echo -e "\n\e[36m--- SonarQube Issues Report ---\e[0m"

# Query for all open issues on this project using curl with Basic Auth (-u)
API_URL="${SONAR_URL}/api/issues/search?componentKeys=${PROJECT_KEY}&statuses=OPEN"
RESPONSE=$(curl -s -u "${SONAR_TOKEN}:" "$API_URL")

# Check if the curl request succeeded and jq can parse the issue count
if [ -z "$RESPONSE" ]; then
    echo -e "\e[31mFailed to fetch report from SonarQube API.\e[0m"
else
    ISSUE_COUNT=$(echo "$RESPONSE" | jq '.issues | length')

    if [ "$ISSUE_COUNT" -eq 0 ] || [ "$ISSUE_COUNT" == "null" ]; then
        echo -e "\e[32mNo open issues found!\e[0m"
    else
        # Parse the JSON and format it as: [Rule] File:Line - Message
        echo "$RESPONSE" | jq -r --arg prefix "${PROJECT_KEY}:" '.issues[] | "[\(.rule)] \(.component | sub($prefix; "")):\(.line // "N/A") - \(.message)"' | while read -r line; do
            echo -e "\e[31m$line\e[0m"
        done
    fi
fi

echo -e "\e[36m-------------------------------\e[0m\n"

# 3. Fail the script if the quality gate failed
if [ "$SONAR_EXIT_CODE" -ne 0 ]; then
    echo -e "\e[31mSonarQube quality gate failed. Fix the issues listed above.\e[0m"
    exit 1
fi

echo "✅ All static analysis passed successfully!"
