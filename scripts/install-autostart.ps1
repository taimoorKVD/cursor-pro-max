# Registers per-user Scheduled Tasks so the orchestrator + Cloudflare tunnel
# start at Windows logon and auto-restart if they crash.
# No admin required. Re-run after changing start scripts.

$ErrorActionPreference = "Stop"

$Pwsh = (Get-Command powershell.exe).Source
$Root = Split-Path -Parent $PSScriptRoot
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function Stop-ScriptInstances([string]$StartScript) {
    $leaf = [System.IO.Path]::GetFileName($StartScript)
    Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = [string]$_.CommandLine
        if ($cmd -and ($cmd -like "*$leaf*" -or $cmd -like "*$StartScript*")) {
            Write-Output "STOP_PID=$($_.ProcessId) script=$leaf"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Register-KeepAliveTask {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$StartScript,
        [Parameter(Mandatory = $true)][string]$Description,
        [int]$DelaySeconds = 0
    )

    if (-not (Test-Path $StartScript)) {
        throw "Missing start script: $StartScript"
    }

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Stop-ScriptInstances $StartScript
    Start-Sleep -Seconds 1

    $action = New-ScheduledTaskAction `
        -Execute $Pwsh `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
    if ($DelaySeconds -gt 0) {
        $trigger.Delay = "PT${DelaySeconds}S"
    }

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew `
        -WakeToRun

    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $Description `
        -Force | Out-Null

    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2

    $task = Get-ScheduledTask -TaskName $TaskName
    $info = $task | Get-ScheduledTaskInfo
    Write-Output "TASK=$TaskName"
    Write-Output "TASK_STATE=$($task.State)"
    Write-Output "LAST_RESULT=$($info.LastTaskResult)"
    Write-Output "LAST_RUN=$($info.LastRunTime)"
    Write-Output ""
}

Register-KeepAliveTask `
    -TaskName "WhatsAppOrchestratorService" `
    -StartScript (Join-Path $PSScriptRoot "start-orchestrator.ps1") `
    -Description "Keeps uvicorn (WhatsApp Cursor Orchestrator) listening on http://127.0.0.1:8000." `
    -DelaySeconds 5

Register-KeepAliveTask `
    -TaskName "WhatsAppOrchestratorCloudflareTunnel" `
    -StartScript (Join-Path $PSScriptRoot "start-cloudflare-tunnel.ps1") `
    -Description "Keeps Cloudflare quick tunnel pointing at http://127.0.0.1:8000 for /chat and webhooks." `
    -DelaySeconds 20

Write-Output "URL_FILE=$(Join-Path $Root 'data\logs\cloudflared-public-url.txt')"
Write-Output "ORCH_LOG=$(Join-Path $Root 'data\logs\orchestrator-uvicorn.log')"
Write-Output "TUNNEL_LOG=$(Join-Path $Root 'data\logs\cloudflared-tunnel.log')"
Write-Output "CHAT_LOCAL=http://127.0.0.1:8000/chat"
Write-Output "NOTE=Both tasks start at Windows logon; Task Scheduler restarts them within ~1 minute if the supervisor exits."
Write-Output "NOTE=Tunnel supervisor self-heals dead quick tunnels, API timeouts, and failed public /health probes."
Write-Output "NOTE=Laptop must be awake/online. Sleep/hibernate pauses them until resume + restart policy."
Write-Output "NOTE=Quick tunnel URL can change after recycle; email + cloudflared-public-url.txt update automatically."
