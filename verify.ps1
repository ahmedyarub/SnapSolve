# Stop execution on any error
$ErrorActionPreference = "Stop"

Write-Host "🔍 Starting Static Analysis & Verification Loop..." -ForegroundColor Cyan

try
{
    # 1. Python: Ruff
    Write-Host "Running Python Checks (Ruff)..." -ForegroundColor Yellow
    ruff check .
    ruff format --check .

    # 2. C++ & Java: Formatting
    Write-Host "Running C++ / Java Format Checks..." -ForegroundColor Yellow
    # Get all relevant files and pipe them to clang-format
    Get-ChildItem -Path . -Include *.cpp, *.hpp, *.c, *.h, *.java -Recurse | ForEach-Object {
        & clang-format --dry-run --Werror $_.FullName
        if ($LASTEXITCODE -ne 0)
        {
            throw "Clang-format check failed on $( $_.Name )"
        }
    }

    # 3. JetBrains Qodana
    Write-Host "Running IDE Inspections (Qodana)..." -ForegroundColor Yellow
    qodana scan --fail-threshold 0 --print-problems

    # 4. SonarQube Scanner
    Write-Host "Running SonarQube Quality Gate..." -ForegroundColor Yellow
    sonar-scanner.bat -Dsonar.qualitygate.wait=true

    Write-Host "✅ All static analysis passed successfully!" -ForegroundColor Green
}
catch
{
    Write-Host "❌ Verification Failed: $_" -ForegroundColor Red
    # Return a non-zero exit code so the AI knows to fix the issue
    exit 1
}