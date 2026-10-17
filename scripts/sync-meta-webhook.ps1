# Sync the current (or provided) public tunnel URL to Meta webhook overrides.
# Requires META_ACCESS_TOKEN + META_VERIFY_TOKEN and META_PHONE_NUMBER_ID and/or META_WABA_ID.

param(
    [string]$PublicUrl = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "data\logs"
$ControlLog = Join-Path $LogDir "cloudflared-control.log"
$UrlFile = Join-Path $LogDir "cloudflared-public-url.txt"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { (Get-Command python -ErrorAction Stop).Source }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
    $line = "{0:u} {1}" -f (Get-Date).ToUniversalTime(), $Message
    Add-Content -Path $ControlLog -Value $line
    Write-Output $Message
}

if (-not $PublicUrl) {
    if (-not (Test-Path $UrlFile)) {
        throw "No -PublicUrl and missing $UrlFile"
    }
    $PublicUrl = (Get-Content -Path $UrlFile -Raw).Trim()
}

$PublicUrl = $PublicUrl.Trim().TrimEnd("/")
if ($PublicUrl -notmatch '^https://(?!api\.)[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+\.trycloudflare\.com$') {
    Write-Log "META_SYNC_SKIP invalid tunnel URL $PublicUrl"
    exit 2
}

# Meta verifies the endpoint during override setup; wait until tunnel + app answer.
$healthUrl = ($PublicUrl -replace '/webhook$', '') + "/health"
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 12
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}
if (-not $ready) {
    Write-Log "META_SYNC_WAIT_FAILED health check did not succeed for $healthUrl"
    exit 3
}

$args = @("-m", "orchestrator.meta_webhook_sync", $PublicUrl)
if ($Force) { $args += "--force" }

Write-Log "META_SYNC_START $PublicUrl"
Push-Location $Root
try {
    & $Python @args
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Log "META_SYNC_EXIT code=$code"
exit $code
