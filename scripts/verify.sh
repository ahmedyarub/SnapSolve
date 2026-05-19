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

# Parse sonar.exclusions from sonar-project.properties to filter out stale issues
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROPS_FILE="$SCRIPT_DIR/../sonar-project.properties"
EXCLUSION_PATTERNS=""
if [ -f "$PROPS_FILE" ]; then
    EXCLUSION_LINE=$(grep "^sonar\.exclusions=" "$PROPS_FILE" | sed 's/^sonar\.exclusions=//')
    if [ -n "$EXCLUSION_LINE" ]; then
        # Convert sonar glob patterns to grep-compatible regex, one per line
        EXCLUSION_PATTERNS=$(echo "$EXCLUSION_LINE" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r pat; do
            pat=$(echo "$pat" | sed 's/\./\\./g; s|\*\*/|(.+/)?|g; s/\*/[^/]*/g')
            echo "^$pat"
        done)
    fi
fi

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
        # Filter out issues from excluded paths
        if [ -n "$EXCLUSION_PATTERNS" ]; then
            FILTERED_RESPONSE=$(echo "$ISSUES_RESPONSE" | jq --arg prefix "${PROJECT_KEY}:" --arg patterns "$EXCLUSION_PATTERNS" '
                .issues | map(
                    select(
                        (.component | sub($prefix; "")) as $path |
                        ($patterns | split("\n") | map(select(length > 0)) | all(. as $pat | $path | test($pat) | not))
                    )
                )
            ')
        else
            FILTERED_RESPONSE=$(echo "$ISSUES_RESPONSE" | jq '.issues')
        fi

        ISSUE_COUNT=$(echo "$FILTERED_RESPONSE" | jq 'length')
    fi

    if [ "$ISSUE_COUNT" -eq 0 ] || [ "$ISSUE_COUNT" == "null" ]; then
        echo -e "\e[32mNo issues found!\e[0m"
    else
        # Parse the JSON and format it as: [Rule] File:Line - Message [Severity]
        echo "$FILTERED_RESPONSE" | jq -r --arg prefix "${PROJECT_KEY}:" '.[] | "[\(.rule)] \(.component | sub($prefix; "")):\(.textRange.startLine // "N/A") - \(.message) [\(.severity)]"' | while read -r line; do
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
