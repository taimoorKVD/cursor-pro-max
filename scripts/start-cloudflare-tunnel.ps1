# Keeps a Cloudflare quick tunnel pointed at the local orchestrator.
# Self-healing supervisor:
#   - waits for uvicorn before starting cloudflared
#   - restarts on exit, API failures, or "Tunnel not found"
#   - probes the public /health URL and recycles a dead tunnel
#   - emails + Meta-sync only when a real quick-tunnel URL changes
# Scheduled Task should keep this script running; the loop never exits on purpose.

$ErrorActionPreference = "Continue"

$Cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$TargetUrl = "http://127.0.0.1:8000"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "data\logs"
$ControlLog = Join-Path $LogDir "cloudflared-control.log"
$CombinedLog = Join-Path $LogDir "cloudflared-tunnel.log"
$StdoutLog = Join-Path $LogDir "cloudflared-session.out.log"
$StderrLog = Join-Path $LogDir "cloudflared-session.err.log"
$UrlFile = Join-Path $LogDir "cloudflared-public-url.txt"
$PidFile = Join-Path $LogDir "cloudflared-tunnel.pid"
$SyncScript = Join-Path $PSScriptRoot "sync-meta-webhook.ps1"
$NotifyScript = Join-Path $PSScriptRoot "notify-tunnel-url.ps1"

# Quick-tunnel hostnames look like word-word-word.trycloudflare.com (never api.trycloudflare.com).
$UrlPattern = 'https://(?!api\.)[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+\.trycloudflare\.com'
$FatalPatterns = @(
    'Unauthorized:\s*Tunnel not found',
    'failed to request quick Tunnel',
    'context deadline exceeded'
)

$HealthIntervalSec = 45
$HealthFailLimit = 3
$UrlWaitSec = 90
$MinBackoffSec = 5
$MaxBackoffSec = 120

$script:syncedUrl = ""
$script:currentUrl = ""
$backoffSec = $MinBackoffSec

if (-not (Test-Path $Cloudflared)) {
    throw "cloudflared not found at $Cloudflared"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
    $line = "{0:u} {1}" -f (Get-Date).ToUniversalTime(), $Message
    Add-Content -Path $ControlLog -Value $line -Encoding utf8
}

function Test-LocalOrchestrator {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    } catch {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $iar = $tcp.BeginConnect("127.0.0.1", 8000, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(400)
            if ($ok -and $tcp.Connected) {
                $tcp.EndConnect($iar)
                $tcp.Close()
                return $true
            }
            $tcp.Close()
        } catch { }
        return $false
    }
}

function Wait-ForOrchestrator {
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline) {
        if (Test-LocalOrchestrator) {
            Write-Log "Orchestrator is listening on 127.0.0.1:8000"
            return
        }
        Write-Log "Waiting for orchestrator on 127.0.0.1:8000..."
        Start-Sleep -Seconds 3
    }
    Write-Log "WARN orchestrator not up after 5 minutes; starting tunnel anyway"
}

function Stop-CloudflaredChildren {
    Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -and $_.CommandLine -match '--url\s+http://127\.0\.0\.1:8000') {
            Write-Log "Stopping existing cloudflared PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

function Clear-PublicUrl([string]$Reason) {
    if (Test-Path $UrlFile) {
        Write-Log "TUNNEL_DOWN clear URL ($Reason) was=$script:currentUrl"
        Remove-Item -Force -ErrorAction SilentlyContinue $UrlFile
    }
    $script:currentUrl = ""
    $script:syncedUrl = ""
}

function Test-PublicHealth([string]$PublicUrl) {
    if (-not $PublicUrl) { return $false }
    $healthUrl = $PublicUrl.TrimEnd("/") + "/health"
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 12
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Sync-MetaWebhook([string]$PublicUrl) {
    if (-not $PublicUrl) { return }
    if ($PublicUrl -eq $script:syncedUrl) { return }
    if (-not (Test-Path $SyncScript)) {
        Write-Log "META_SYNC_SKIP missing $SyncScript"
        return
    }
    Write-Log "META_SYNC_TRIGGER $PublicUrl"
    try {
        # Background so a slow Meta API never blocks tunnel supervision.
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList @(
                "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", $SyncScript, "-PublicUrl", $PublicUrl
            ) `
            -WindowStyle Hidden | Out-Null
        $script:syncedUrl = $PublicUrl
    } catch {
        Write-Log "META_SYNC_ERROR $($_.Exception.Message)"
    }
}

function Send-UrlChangeEmail([string]$PublicUrl, [string]$PreviousUrl) {
    if (-not $PublicUrl) { return }
    if (-not (Test-Path $NotifyScript)) {
        Write-Log "URL_EMAIL_SKIP missing $NotifyScript"
        return
    }
    Write-Log "URL_EMAIL_TRIGGER $PublicUrl"
    try {
        # Empty PreviousUrl must not be passed: external powershell drops "" and
        # leaves -PreviousUrl with no value (MissingArgument).
        $notifyArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", $NotifyScript,
            "-PublicUrl", $PublicUrl
        )
        if (-not [string]::IsNullOrWhiteSpace($PreviousUrl)) {
            $notifyArgs += @("-PreviousUrl", $PreviousUrl)
        }
        & powershell.exe @notifyArgs
        Write-Log "URL_EMAIL_DONE exit=$LASTEXITCODE"
    } catch {
        Write-Log "URL_EMAIL_ERROR $($_.Exception.Message)"
    }
}

function Set-PublicUrl([string]$Url) {
    if (-not $Url) { return }
    if ($Url -eq $script:currentUrl) { return }

    $previous = ""
    if (Test-Path $UrlFile) {
        $previous = (Get-Content -Path $UrlFile -Raw).Trim()
    }

    [System.IO.File]::WriteAllText($UrlFile, $Url)
    $script:currentUrl = $Url
    Write-Log "Public URL: $Url"

    if ($Url -ne $previous) {
        Send-UrlChangeEmail $Url $previous
        Sync-MetaWebhook $Url
    } elseif (-not $script:syncedUrl) {
        Sync-MetaWebhook $Url
    }
}

function Read-NewLogLines([string]$Path, [ref]$Offset) {
    $lines = @()
    if (-not (Test-Path $Path)) { return $lines }
    try {
        $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            if ($Offset.Value -gt $fs.Length) { $Offset.Value = 0 }
            $fs.Seek($Offset.Value, [System.IO.SeekOrigin]::Begin) | Out-Null
            $reader = New-Object System.IO.StreamReader($fs)
            while ($null -ne ($line = $reader.ReadLine())) {
                $lines += $line
            }
            $Offset.Value = $fs.Position
            $reader.Dispose()
        } finally {
            $fs.Dispose()
        }
    } catch { }
    return $lines
}

function Test-FatalLine([string]$Text) {
    foreach ($pat in $FatalPatterns) {
        if ($Text -match $pat) { return $true }
    }
    return $false
}

function Start-CloudflaredProcess {
    Remove-Item -Force -ErrorAction SilentlyContinue $StdoutLog, $StderrLog, $PidFile
    Add-Content -Path $CombinedLog -Value ("`n---- {0:u} start ----" -f (Get-Date).ToUniversalTime()) -Encoding utf8

    $proc = Start-Process -FilePath $Cloudflared `
        -ArgumentList @("tunnel", "--url", $TargetUrl) `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -PassThru

    [System.IO.File]::WriteAllText($PidFile, "$($proc.Id)")
    Write-Log "cloudflared started PID $($proc.Id)"
    return $proc
}

Write-Log "Tunnel supervisor starting -> $TargetUrl"

while ($true) {
    try {
        Wait-ForOrchestrator
        Stop-CloudflaredChildren

        $proc = Start-CloudflaredProcess
        $outOffset = [int64]0
        $errOffset = [int64]0
        $startedAt = Get-Date
        $gotUrl = $false
        $healthFails = 0
        $lastHealthAt = Get-Date
        $recycleReason = ""

        while (-not $proc.HasExited) {
            $newLines = @()
            $newLines += Read-NewLogLines $StdoutLog ([ref]$outOffset)
            $newLines += Read-NewLogLines $StderrLog ([ref]$errOffset)

            foreach ($text in $newLines) {
                Add-Content -Path $CombinedLog -Value $text -Encoding utf8

                $m = [regex]::Match($text, $UrlPattern)
                if ($m.Success) {
                    Set-PublicUrl $m.Value
                    $gotUrl = $true
                    $backoffSec = $MinBackoffSec
                    $healthFails = 0
                }

                if (Test-FatalLine $text) {
                    $recycleReason = "fatal-log"
                    Write-Log "TUNNEL_FATAL $text"
                    break
                }
            }

            if ($recycleReason) { break }

            if (-not $gotUrl -and ((Get-Date) - $startedAt).TotalSeconds -ge $UrlWaitSec) {
                $recycleReason = "no-url-timeout"
                Write-Log "TUNNEL_FATAL no public URL within ${UrlWaitSec}s"
                break
            }

            if ($gotUrl -and ((Get-Date) - $lastHealthAt).TotalSeconds -ge $HealthIntervalSec) {
                $lastHealthAt = Get-Date
                if (Test-PublicHealth $script:currentUrl) {
                    $healthFails = 0
                } else {
                    $healthFails++
                    Write-Log "PUBLIC_HEALTH_FAIL count=$healthFails url=$script:currentUrl"
                    if ($healthFails -ge $HealthFailLimit) {
                        $recycleReason = "public-health"
                        break
                    }
                }
            }

            Start-Sleep -Seconds 2
            try { $proc.Refresh() } catch { break }
        }

        if (-not $recycleReason) {
            $recycleReason = "process-exit code=$($proc.ExitCode)"
        }

        if (-not $proc.HasExited) {
            Write-Log "Stopping cloudflared PID $($proc.Id) reason=$recycleReason"
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            try { $proc.WaitForExit(8000) | Out-Null } catch { }
        } else {
            Write-Log "cloudflared exited code=$($proc.ExitCode) reason=$recycleReason"
        }

        Stop-CloudflaredChildren
        Clear-PublicUrl $recycleReason
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue

        Write-Log "Tunnel recycle sleep ${backoffSec}s"
        Start-Sleep -Seconds $backoffSec
        if ($backoffSec -lt $MaxBackoffSec) {
            $backoffSec = [Math]::Min($MaxBackoffSec, [int]($backoffSec * 2))
        }
    } catch {
        Write-Log ("Tunnel supervisor error: " + $_.Exception.Message)
        Start-Sleep -Seconds $backoffSec
        if ($backoffSec -lt $MaxBackoffSec) {
            $backoffSec = [Math]::Min($MaxBackoffSec, [int]($backoffSec * 2))
        }
    }
}
