# Stop execution on any error
$ErrorActionPreference = "Stop"

Write-Host "🔍 Starting Static Analysis & Verification Loop..." -ForegroundColor Cyan

try
{
    # 1. Python: Ruff
    Write-Host "Running Python Checks (Ruff)..." -ForegroundColor Yellow
    ruff check . --exclude "services/whisperlive"
    if ($LASTEXITCODE -ne 0)
    {
        throw "Ruff check failed."
    }
    ruff format --check . --exclude "services/whisperlive" --exclude "android_remote_control/build" --exclude "android_remote_control/app/build" --exclude "android_remote_control/gradle"
    if ($LASTEXITCODE -ne 0)
    {
        throw "Ruff format check failed."
    }

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

    # Populate SonarToken from environment variable
    $SonarToken = $env:SONAR_TOKEN

    # 1. Run the container
    wsl bash -c "docker start sonarqube"

    # 2. Run the scanner
    sonar-scanner.bat "-Dsonar.qualitygate.wait=true" "-Dsonar.python.version=3"
    $sonarExitCode = $LASTEXITCODE

    # 3. Fetch the issues directly from the SonarQube API
    $SonarUrl = "http://localhost:9000"
    $ProjectKey = "SnapSolve"  # Update this to your exact sonar.projectKey

    # Encode token for Basic Auth (Sonar uses token as username, blank password)
    $Bytes = [System.Text.Encoding]::ASCII.GetBytes("${SonarToken}:")
    $Base64 = [System.Convert]::ToBase64String($Bytes)
    $Headers = @{ Authorization = "Basic $Base64" }

    Write-Host "`n--- SonarQube Issues Report ---" -ForegroundColor Cyan

    try
    {
        # Parse sonar.exclusions from sonar-project.properties to filter out stale issues
        $ExclusionPatterns = @()
        $PropsFile = Join-Path $PSScriptRoot "..\sonar-project.properties"
        if (Test-Path $PropsFile)
        {
            $ExclusionLine = (Get-Content $PropsFile | Where-Object { $_ -match "^sonar\.exclusions=" }) -replace "^sonar\.exclusions=", ""
            if ($ExclusionLine)
            {
                # Convert sonar glob patterns (e.g. **/build/**) to regex patterns
                $ExclusionPatterns = $ExclusionLine -split "," | ForEach-Object {
                    $pattern = $_.Trim()
                    $pattern = $pattern -replace "\.", "\."
                    $pattern = $pattern -replace "\*\*/", "(.+/)?"
                    $pattern = $pattern -replace "\*", "[^/]*"
                    "^$pattern"
                }
            }
        }

        # Wait for SonarQube analysis to complete on the server
        $ScannerWorkDir = Join-Path $PSScriptRoot "../.scannerwork"
        $ReportTaskFile = Join-Path $ScannerWorkDir "report-task.txt"
        $AnalysisDate = $null
        if (Test-Path $ReportTaskFile)
        {
            $CeTaskUrl = (Get-Content $ReportTaskFile | Where-Object { $_ -match "^ceTaskUrl=" }) -replace "^ceTaskUrl=", ""
            if ($CeTaskUrl)
            {
                Write-Host "Waiting for server-side analysis to complete..." -ForegroundColor Yellow
                $maxWait = 60
                $waited = 0
                while ($waited -lt $maxWait)
                {
                    try
                    {
                        $TaskResponse = Invoke-RestMethod -Uri $CeTaskUrl -Headers $Headers -Method Get
                        $TaskStatus = $TaskResponse.task.status
                        if ($TaskStatus -eq "SUCCESS")
                        {
                            $AnalysisDate = $TaskResponse.task.startedAt
                            Write-Host "Analysis completed." -ForegroundColor Green
                            break
                        }
                        elseif ($TaskStatus -eq "FAILED" -or $TaskStatus -eq "CANCELED")
                        {
                            Write-Host "Analysis task $TaskStatus." -ForegroundColor Red
                            break
                        }
                    }
                    catch
                    {
                        Write-Host "Waiting for analysis..." -ForegroundColor Yellow
                    }
                    Start-Sleep -Seconds 2
                    $waited += 2
                }
            }
        }

        # Query for issues (only open/confirmed/reopened)
        $ApiUrl = "$SonarUrl/api/issues/search?componentKeys=$ProjectKey&types=CODE_SMELL,BUG,VULNERABILITY&statuses=OPEN,CONFIRMED,REOPENED"
        $IssuesResponse = Invoke-RestMethod -Uri $ApiUrl -Headers $Headers -Method Get

        # Filter out issues from excluded paths
        $filteredIssues = $IssuesResponse.issues | Where-Object {
            $filePath = $_.component.Replace("${ProjectKey}:", "")
            $excluded = $false
            foreach ($pattern in $ExclusionPatterns)
            {
                if ($filePath -match $pattern)
                {
                    $excluded = $true
                    break
                }
            }
            -not $excluded
        }

        if ($filteredIssues.Count -eq 0)
        {
            Write-Host "No issues found!" -ForegroundColor Green
        }
        else
        {
            foreach ($issue in $filteredIssues)
            {
                # Format: [Rule] File:Line - Message (Severity)
                $filePath = $issue.component.Replace("${ProjectKey}:", "")
                $line = if ($issue.textRange) { $issue.textRange.startLine } else { "N/A" }
                $severity = $issue.severity
                Write-Host "[$( $issue.rule )] $( $filePath ):$( $line ) - $( $issue.message ) [$severity]" -ForegroundColor Red
            }
        }
    }
    catch
    {
        Write-Host "Failed to fetch issues from SonarQube API: $_" -ForegroundColor DarkRed
    }

    # 4. Fetch Security Hotspots
    Write-Host "`n--- Security Hotspots Report ---" -ForegroundColor Cyan

    try
    {
        $HotspotsUrl = "$SonarUrl/api/hotspots/search?projectKey=$ProjectKey&status=TO_REVIEW"
        $HotspotsResponse = Invoke-RestMethod -Uri $HotspotsUrl -Headers $Headers -Method Get

        # Filter out hotspots from excluded paths
        $filteredHotspots = $HotspotsResponse.hotspots | Where-Object {
            $filePath = $_.component.Replace("${ProjectKey}:", "")
            $excluded = $false
            foreach ($pattern in $ExclusionPatterns)
            {
                if ($filePath -match $pattern)
                {
                    $excluded = $true
                    break
                }
            }
            -not $excluded
        }

        if ($filteredHotspots.Count -eq 0)
        {
            Write-Host "No security hotspots to review!" -ForegroundColor Green
        }
        else
        {
            foreach ($hotspot in $filteredHotspots)
            {
                $filePath = $hotspot.component.Replace("${ProjectKey}:", "")
                $line = if ($hotspot.textRange) { $hotspot.textRange.startLine } else { "N/A" }
                $vulnerability = $hotspot.vulnerabilityProbability
                Write-Host "[$( $hotspot.securityCategory )] $( $filePath ):$( $line ) - $( $hotspot.message ) [$vulnerability]" -ForegroundColor Magenta
            }
        }
    }
    catch
    {
        if ($_.ToString() -match "Insufficient privileges" -or $_.Exception.Response.StatusCode -eq 403)
        {
            Write-Host "Skipped: Token lacks 'Browse' permission for hotspots. Grant it at: $SonarUrl/project/permissions?id=$ProjectKey" -ForegroundColor DarkYellow
        }
        else
        {
            Write-Host "Failed to fetch security hotspots from SonarQube API: $_" -ForegroundColor DarkRed
        }
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