# Stop execution on any error
$ErrorActionPreference = "Stop"

Write-Host "🔍 Starting Static Analysis & Verification Loop..." -ForegroundColor Cyan

try
{
    # 1. Python: Ruff
    Write-Host "Running Python Checks (Ruff)..." -ForegroundColor Yellow
    ruff check .
    ruff format --check .

    # 2. JetBrains Qodana
    Write-Host "Running IDE Inspections (Qodana via WSL)..." -ForegroundColor Yellow

    # Execute the Linux Qodana CLI inside WSL, passing the environment variable inline.
    # WSL automatically maps your current E:\ drive path to /mnt/e/
    wsl bash -c "NONINTERACTIVE=true qodana scan --fail-threshold 0 --print-problems --apply-fixes"

    # Capture the exit code from the WSL process to halt the AI if issues are found
    if ($LASTEXITCODE -ne 0)
    {
        throw "Qodana inspection failed."
    }

    # 3. SonarQube Scanner
    Write-Host "Running SonarQube Quality Gate..." -ForegroundColor Yellow
    sonar-scanner.bat "-Dsonar.qualitygate.wait=true"

    Write-Host "✅ All static analysis passed successfully!" -ForegroundColor Green
}
catch
{
    Write-Host "❌ Verification Failed: $_" -ForegroundColor Red
    # Return a non-zero exit code so the AI knows to fix the issue
    exit 1
}