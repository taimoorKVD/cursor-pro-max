# Starts the local FastAPI orchestrator (uvicorn) and keeps it running.
# Restarts uvicorn when .env, projects.json, or application code changes.
# Reloads are debounced + cooled down so rapid file saves (agents/editors)
# do not thrash the process and flood Cloudflare with 502s.

$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "data\logs"
$ControlLog = Join-Path $LogDir "orchestrator-control.log"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"
$ProjectsFile = Join-Path $Root "projects.json"
$RestartRequestFile = Join-Path $Root "data\restart-orchestrator.request"
$HostAddr = "127.0.0.1"
$Port = 8000
# Wait until watched stamps stop changing before killing uvicorn.
$ReloadSettleSec = 3
# Minimum gap between reloads (prevents restart storms during multi-file edits).
$ReloadCooldownSec = 12
# After a reload, ignore flaky health while uvicorn is still binding.
$BootGraceSec = 15

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
    # Shared append: Add-Content fails with "Stream was not readable" / lock errors
    # when another process (viewer, second supervisor, AV) has the log open.
    $line = ("{0:u} {1}" -f (Get-Date).ToUniversalTime(), $Message) + [Environment]::NewLine
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($line)
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        $fs = $null
        try {
            $fs = [System.IO.File]::Open(
                $ControlLog,
                [System.IO.FileMode]::Append,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::ReadWrite
            )
            $fs.Write($bytes, 0, $bytes.Length)
            return
        } catch {
            Start-Sleep -Milliseconds (40 * ($attempt + 1))
        } finally {
            if ($null -ne $fs) { $fs.Dispose() }
        }
    }
}

function Get-CodeStamp {
    $files = @()
    $app = Join-Path $Root "app.py"
    if (Test-Path -LiteralPath $app) { $files += Get-Item -LiteralPath $app }
    $codeRoot = Join-Path $Root "orchestrator"
    if (Test-Path -LiteralPath $codeRoot) {
        $files += Get-ChildItem -LiteralPath $codeRoot -Recurse -File -Include *.py,*.css -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '\\__pycache__\\' }
    }
    $maxTicks = [int64]0
    $len = [int64]0
    foreach ($f in $files) {
        if ($f.LastWriteTimeUtc.Ticks -gt $maxTicks) { $maxTicks = [int64]$f.LastWriteTimeUtc.Ticks }
        $len += [int64]$f.Length
    }
    return [pscustomobject]@{ Count = @($files).Count; Length = $len; Ticks = $maxTicks }
}

function Get-FileStamp([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{ Exists = $false; Length = [int64](-1); Ticks = [int64]0 }
    }
    $item = Get-Item -LiteralPath $Path
    return [pscustomobject]@{
        Exists = $true
        Length = [int64]$item.Length
        Ticks  = [int64]$item.LastWriteTimeUtc.Ticks
    }
}

function Test-PortListen {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect($HostAddr, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(350)
        if ($ok -and $c.Connected) {
            $c.EndConnect($iar)
            $c.Close()
            return $true
        }
        $c.Close()
    } catch { }
    return $false
}

function Test-OrchestratorHealth {
    try {
        $resp = Invoke-WebRequest -Uri "http://${HostAddr}:$Port/health" -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Get-ListenersOnPort([int]$ListenPort) {
    $pids = @()
    try {
        $lines = netstat -ano -p tcp | Select-String -Pattern "^\s*TCP\s+\S+:$ListenPort\s+\S+\s+LISTENING\s+(\d+)" -AllMatches
        foreach ($m in $lines) {
            if ($m.Matches.Count -gt 0) {
                $pids += [int]$m.Matches[0].Groups[1].Value
            }
        }
    } catch { }
    return ($pids | Select-Object -Unique)
}

function Stop-OrchestratorProcesses {
    # Match --port 8000 (venv/supervisor) and any uvicorn app:app bound to this port.
    # Older check looked for ":8000", which missed "--port 8000" and left orphan uvicorn alive.
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = [string]$_.CommandLine
        if (-not $cmd) { return }
        $isUvicorn = $cmd -match 'uvicorn\s+app:app'
        $isOurPort = ($cmd -match "--port\s+$Port") -or ($cmd -match [regex]::Escape(":${Port}"))
        if ($isUvicorn -and $isOurPort) {
            Write-Log "Stopping uvicorn PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($pid in (Get-ListenersOnPort $Port)) {
        Write-Log "Stopping port-$Port listener PID $pid"
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 900
}

function Test-StampEqual($a, $b) {
    return ($a.Count -eq $b.Count) -and ($a.Length -eq $b.Length) -and ($a.Ticks -eq $b.Ticks)
}

function Test-FileStampEqual($a, $b) {
    return ($a.Exists -eq $b.Exists) -and ($a.Length -eq $b.Length) -and ($a.Ticks -eq $b.Ticks)
}

function Wait-WatchedStampsSettle {
    # Keep sampling until .env / projects / code stamps are unchanged for ReloadSettleSec.
    $deadline = [datetime]::UtcNow.AddSeconds([math]::Max(1, $ReloadSettleSec))
    $envS = Get-FileStamp $EnvFile
    $projS = Get-FileStamp $ProjectsFile
    $codeS = Get-CodeStamp
    while ([datetime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $envN = Get-FileStamp $EnvFile
        $projN = Get-FileStamp $ProjectsFile
        $codeN = Get-CodeStamp
        if ((Test-FileStampEqual $envS $envN) -and (Test-FileStampEqual $projS $projN) -and (Test-StampEqual $codeS $codeN)) {
            continue
        }
        $envS = $envN; $projS = $projN; $codeS = $codeN
        $deadline = [datetime]::UtcNow.AddSeconds([math]::Max(1, $ReloadSettleSec))
    }
    return [pscustomobject]@{ Env = $envS; Projects = $projS; Code = $codeS }
}

function Start-Uvicorn([string]$Reason) {
    Stop-OrchestratorProcesses
    Write-Log "Starting uvicorn -> http://${HostAddr}:$Port ($Reason)"
    $proc = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", $HostAddr, "--port", "$Port") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -PassThru
    Start-Sleep -Seconds 2
    # Evict stray listeners that are NOT our uvicorn process or its worker child.
    # (venv uvicorn often spawns a base-interpreter worker that actually binds the port.)
    foreach ($listenPid in (Get-ListenersOnPort $Port)) {
        if ($proc -and $listenPid -eq $proc.Id) { continue }
        $other = Get-CimInstance Win32_Process -Filter "ProcessId = $listenPid" -ErrorAction SilentlyContinue
        if ($proc -and $other -and [int]$other.ParentProcessId -eq $proc.Id) { continue }
        $cmd = if ($other) { [string]$other.CommandLine } else { "" }
        if ($cmd -and $cmd -like "*$Python*") { continue }
        Write-Log "Evicting foreign listener PID $listenPid"
        Stop-Process -Id $listenPid -Force -ErrorAction SilentlyContinue
    }
    # Wait briefly for /health so cloudflared stops 502'ing as soon as possible.
    for ($i = 0; $i -lt 20; $i++) {
        if (Test-OrchestratorHealth) { break }
        Start-Sleep -Milliseconds 250
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Log "Missing venv python: $Python"
    exit 1
}

Write-Log "Orchestrator supervisor starting (watches .env, projects.json, and application code; settle=${ReloadSettleSec}s cooldown=${ReloadCooldownSec}s)"
$envStamp = Get-FileStamp $EnvFile
$projStamp = Get-FileStamp $ProjectsFile
$codeStamp = Get-CodeStamp
Write-Log ("Initial .env length={0} projects length={1} code files={2}" -f $envStamp.Length, $projStamp.Length, $codeStamp.Count)
Start-Uvicorn "initial"
$lastReloadAt = [datetime]::UtcNow

$heartbeatAt = [datetime]::UtcNow
while ($true) {
    Start-Sleep -Seconds 1

    if (([datetime]::UtcNow - $heartbeatAt).TotalSeconds -ge 20) {
        $e = Get-FileStamp $EnvFile
        Write-Log ("Heartbeat listen={0} health={1} envLen={2}" -f (Test-PortListen), (Test-OrchestratorHealth), $e.Length)
        $heartbeatAt = [datetime]::UtcNow
    }

    try {
        $sinceReload = ([datetime]::UtcNow - $lastReloadAt).TotalSeconds
        if (-not (Test-PortListen) -or -not (Test-OrchestratorHealth)) {
            if ($sinceReload -lt $BootGraceSec) {
                # Expected gap while uvicorn binds after a reload — do not thrash.
                continue
            }
            Write-Log "Orchestrator unhealthy (port/health) - restarting"
            Start-Uvicorn "health-down"
            $lastReloadAt = [datetime]::UtcNow
            $envStamp = Get-FileStamp $EnvFile
            $projStamp = Get-FileStamp $ProjectsFile
            $codeStamp = Get-CodeStamp
            continue
        }

        if (Test-Path -LiteralPath $RestartRequestFile) {
            if ($sinceReload -lt $ReloadCooldownSec) {
                continue
            }
            Write-Log "Manual restart requested via webchat"
            Remove-Item -LiteralPath $RestartRequestFile -Force -ErrorAction SilentlyContinue
            Start-Uvicorn "manual-request"
            $lastReloadAt = [datetime]::UtcNow
            $envStamp = Get-FileStamp $EnvFile
            $projStamp = Get-FileStamp $ProjectsFile
            $codeStamp = Get-CodeStamp
            Write-Log "Manual reload complete"
            continue
        }

        $envNow = Get-FileStamp $EnvFile
        $projNow = Get-FileStamp $ProjectsFile
        $codeNow = Get-CodeStamp
        $envChanged = -not (Test-FileStampEqual $envStamp $envNow)
        $projChanged = -not (Test-FileStampEqual $projStamp $projNow)
        $codeChanged = -not (Test-StampEqual $codeStamp $codeNow)

        if ($envChanged -or $projChanged -or $codeChanged) {
            if ($sinceReload -lt $ReloadCooldownSec) {
                continue
            }
            $reason = if ($codeChanged -and -not $envChanged -and -not $projChanged) { "code-change" } else { "config-change" }
            Write-Log ("Watched files changed - settling before reload ($reason)")
            $settled = Wait-WatchedStampsSettle
            $envStamp = $settled.Env
            $projStamp = $settled.Projects
            $codeStamp = $settled.Code
            # Re-check cooldown after settle (long edit bursts).
            if (([datetime]::UtcNow - $lastReloadAt).TotalSeconds -lt $ReloadCooldownSec) {
                continue
            }
            Write-Log ("Restarting uvicorn ($reason)")
            Start-Uvicorn $reason
            $lastReloadAt = [datetime]::UtcNow
            $envStamp = Get-FileStamp $EnvFile
            $projStamp = Get-FileStamp $ProjectsFile
            $codeStamp = Get-CodeStamp
            Write-Log "Reload complete"
        }
    } catch {
        Write-Log ("Supervisor loop error: " + $_.Exception.Message)
        Start-Sleep -Seconds 2
    }
}
