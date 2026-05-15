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
ruff format --check . --exclude "services/whisperlive" --exclude "android_remote_control/build" --exclude "android_remote_control/app/build" --exclude "android_remote_control/gradle"
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

# 1. Run the container
docker start sonarqube

# 2. Run the scanner
sonar-scanner -Dsonar.qualitygate.wait=true -Dsonar.python.version=3
SONAR_EXIT_CODE=$?

# 3. Fetch the issues directly from the SonarQube API
SONAR_URL="http://localhost:9000"
PROJECT_KEY="SnapSolve" # Update this to your exact sonar.projectKey

echo -e "\n\e[36m--- SonarQube Issues Report ---\e[0m"

# Query for issues
API_URL="${SONAR_URL}/api/issues/search?componentKeys=${PROJECT_KEY}&types=CODE_SMELL,BUG,VULNERABILITY"
ISSUES_RESPONSE=$(curl -s -u "${SONAR_TOKEN}:" "$API_URL")

if [ -z "$ISSUES_RESPONSE" ]; then
    echo -e "\e[31mFailed to fetch issues from SonarQube API (empty response).\e[0m"
else
    # Check if response is valid JSON
    if ! echo "$ISSUES_RESPONSE" | jq empty 2>/dev/null; then
        echo -e "\e[31mFailed to fetch issues from SonarQube API (invalid JSON response).\e[0m"
        echo -e "\e[31mResponse: $ISSUES_RESPONSE\e[0m"
    else
        ISSUE_COUNT=$(echo "$ISSUES_RESPONSE" | jq '.issues | length')
    fi

    if [ "$ISSUE_COUNT" -eq 0 ] || [ "$ISSUE_COUNT" == "null" ]; then
        echo -e "\e[32mNo issues found!\e[0m"
    else
        # Parse the JSON and format it as: [Rule] File:Line - Message [Severity]
        echo "$ISSUES_RESPONSE" | jq -r --arg prefix "${PROJECT_KEY}:" '.issues[] | "[\(.rule)] \(.component | sub($prefix; "")):\(.textRange.startLine // "N/A") - \(.message) [\(.severity)]"' | while read -r line; do
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
