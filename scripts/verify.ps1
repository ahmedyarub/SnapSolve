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
    Write-Host "Running SonarQube Scanner..." -ForegroundColor Yellow

    # 1. Run the scanner
    sonar-scanner.bat "-Dsonar.qualitygate.wait=true" "-Dsonar.python.version=3"
    $sonarExitCode = $LASTEXITCODE

    # 2. Fetch the issues directly from the SonarQube API
    $SonarUrl = "http://localhost:9000"
    $ProjectKey = "SnapSolve"  # Update this to your exact sonar.projectKey

    # Encode token for Basic Auth (Sonar uses token as username, blank password)
    $Bytes = [System.Text.Encoding]::ASCII.GetBytes("${SonarToken}:")
    $Base64 = [System.Convert]::ToBase64String($Bytes)
    $Headers = @{ Authorization = "Basic $Base64" }

    Write-Host "`n--- SonarQube Issues Report ---" -ForegroundColor Cyan

    try
    {
        # Query for all open issues on this project
        $ApiUrl = "$SonarUrl/api/issues/search?componentKeys=$ProjectKey&statuses=OPEN"
        $Response = Invoke-RestMethod -Uri $ApiUrl -Headers $Headers -Method Get

        if ($Response.issues.Count -eq 0)
        {
            Write-Host "No open issues found!" -ForegroundColor Green
        }
        else
        {
            foreach ($issue in $Response.issues)
            {
                # Format: [Rule] File:Line - Message
                $filePath = $issue.component.Replace("${ProjectKey}:", "")
                Write-Host "[$( $issue.rule )] $( $filePath ):$( $issue.line ) - $( $issue.message )" -ForegroundColor Red
            }
        }
    }
    catch
    {
        Write-Host "Failed to fetch report from SonarQube API." -ForegroundColor DarkRed
    }

    Write-Host "-------------------------------`n" -ForegroundColor Cyan

    # 3. Fail the script if the quality gate failed
    if ($sonarExitCode -ne 0)
    {
        throw "SonarQube quality gate failed. Fix the issues listed above."
    }

    Write-Host "✅ All static analysis passed successfully!" -ForegroundColor Green
}
catch
{
    Write-Host "❌ Verification Failed: $_" -ForegroundColor Red
    # Return a non-zero exit code so the AI knows to fix the issue
    exit 1
}