# Emails the operator when the Cloudflare quick-tunnel public URL changes.
# Reads SMTP settings from the project .env (does not print secrets).

param(
    [Parameter(Mandatory = $true)]
    [string]$PublicUrl,

    [string]$PreviousUrl = "",

    [switch]$Test
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "data\logs"
$ControlLog = Join-Path $LogDir "cloudflared-control.log"
$EnvFile = Join-Path $Root ".env"
$LastEmailedFile = Join-Path $LogDir "cloudflared-last-emailed-url.txt"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
    $line = "{0:u} {1}" -f (Get-Date).ToUniversalTime(), $Message
    Add-Content -Path $ControlLog -Value $line
    Write-Output $Message
}

function Get-DotEnvMap([string]$Path) {
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if (
            ($val.StartsWith('"') -and $val.EndsWith('"')) -or
            ($val.StartsWith("'") -and $val.EndsWith("'"))
        ) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $map[$key] = $val
    }
    return $map
}

function Get-EnvBool([hashtable]$Map, [string]$Key, [bool]$Default = $false) {
    if (-not $Map.ContainsKey($Key) -or [string]::IsNullOrWhiteSpace($Map[$Key])) {
        return $Default
    }
    return @("1", "true", "yes", "on") -contains $Map[$Key].Trim().ToLowerInvariant()
}

function Escape-Html([string]$Text) {
    if ($null -eq $Text) { return "" }
    return [System.Net.WebUtility]::HtmlEncode($Text)
}

$envMap = Get-DotEnvMap $EnvFile
if (-not (Get-EnvBool $envMap "TUNNEL_URL_EMAIL_ENABLED" $true)) {
    Write-Log "URL_EMAIL_SKIP disabled"
    exit 0
}

$PublicUrl = $PublicUrl.Trim().TrimEnd("/")
if (-not $PublicUrl) {
    Write-Log "URL_EMAIL_SKIP empty PublicUrl"
    exit 0
}
# Reject Cloudflare API / non-tunnel hosts that can appear in cloudflared error lines.
if ($PublicUrl -notmatch '^https://(?!api\.)[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+\.trycloudflare\.com$') {
    Write-Log "URL_EMAIL_SKIP invalid tunnel URL $PublicUrl"
    exit 0
}

if (-not $Test -and (Test-Path $LastEmailedFile)) {
    $last = (Get-Content -Path $LastEmailedFile -Raw).Trim()
    if ($last -eq $PublicUrl) {
        Write-Log "URL_EMAIL_SKIP already emailed $PublicUrl"
        exit 0
    }
}

$hostName = $envMap["SMTP_HOST"]
if ([string]::IsNullOrWhiteSpace($hostName)) { $hostName = "mail-eu.smtp2go.com" }
$portText = $envMap["SMTP_PORT"]
if ([string]::IsNullOrWhiteSpace($portText)) { $portText = "2525" }
$port = [int]$portText
$user = $envMap["SMTP_USER"]
$password = $envMap["SMTP_PASSWORD"]
$from = $envMap["SMTP_FROM"]
if ([string]::IsNullOrWhiteSpace($from)) { $from = $user }
$to = $envMap["TUNNEL_URL_NOTIFY_TO"]
if ([string]::IsNullOrWhiteSpace($to)) { $to = "taimoor.kingdomvision@gmail.com" }

if ([string]::IsNullOrWhiteSpace($user) -or [string]::IsNullOrWhiteSpace($password)) {
    Write-Log "URL_EMAIL_SKIP missing SMTP_USER or SMTP_PASSWORD in .env"
    exit 2
}
if ([string]::IsNullOrWhiteSpace($from)) {
    Write-Log "URL_EMAIL_SKIP missing SMTP_FROM"
    exit 2
}

$chatUrl = "$PublicUrl/chat"
$healthUrl = "$PublicUrl/health"
$localChat = "http://127.0.0.1:8000/chat"
$whenLocal = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$whenUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss") + " UTC"
$machine = $env:COMPUTERNAME
$hadPrevious = -not [string]::IsNullOrWhiteSpace($PreviousUrl)
if (-not $hadPrevious) { $PreviousUrl = "(none / first run)" }

$subject = "TaimoorKVD AI Assistant - Configuration Updates"
if ($Test) { $subject = "$subject [TEST]" }

$badgeLabel = if ($Test) { "TEST NOTIFICATION" } else { "URL UPDATED" }
$badgeColor = if ($Test) { "#b45309" } else { "#0f766e" }
$intro = if ($Test) {
    "This is a mock delivery check. SMTP is working. The links below are sample values only."
} else {
    "Your public tunnel address was refreshed. Tap Open Chat on your phone to continue."
}

$ePublic = Escape-Html $PublicUrl
$eChat = Escape-Html $chatUrl
$eHealth = Escape-Html $healthUrl
$eLocal = Escape-Html $localChat
$ePrev = Escape-Html $PreviousUrl
$eWhenLocal = Escape-Html $whenLocal
$eWhenUtc = Escape-Html $whenUtc
$eMachine = Escape-Html $machine
$eIntro = Escape-Html $intro
$eBadge = Escape-Html $badgeLabel

$prevRowHtml = if ($hadPrevious -and $PreviousUrl -match '^https?://') {
    @"
              <tr>
                <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#64748b;width:34%;vertical-align:top;">Previous URL</td>
                <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#0f172a;word-break:break-all;">
                  <a href="$ePrev" style="color:#0f766e;text-decoration:underline;">$ePrev</a>
                </td>
              </tr>
"@
} else {
    @"
              <tr>
                <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#64748b;width:34%;vertical-align:top;">Previous URL</td>
                <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#0f172a;">$ePrev</td>
              </tr>
"@
}

$htmlBody = @"
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>$subject</title>
</head>
<body style="margin:0;padding:0;background:#eef2f4;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef2f4;padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #dbe3e8;">
          <tr>
            <td style="background:linear-gradient(135deg,#0b3b3a 0%,#115e59 55%,#134e4a 100%);background-color:#115e59;padding:28px 28px 24px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <div style="font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:#99f6e4;font-weight:600;">TaimoorKVD</div>
                    <div style="font-size:22px;line-height:1.25;color:#ffffff;font-weight:700;margin-top:6px;">AI Assistant</div>
                    <div style="font-size:14px;color:#ccfbf1;margin-top:8px;">Configuration Updates</div>
                  </td>
                  <td align="right" valign="top" style="width:1%;white-space:nowrap;">
                    <span style="display:inline-block;background:$badgeColor;color:#ffffff;font-size:11px;font-weight:700;letter-spacing:0.06em;padding:7px 10px;border-radius:999px;">$eBadge</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:28px 28px 8px;">
              <p style="margin:0 0 18px;font-size:15px;line-height:1.55;color:#334155;">$eIntro</p>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f8fafb;border:1px solid #e2e8f0;border-radius:12px;">
                <tr>
                  <td style="padding:18px 18px 8px;">
                    <div style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;font-weight:700;">New chat access</div>
                    <div style="margin-top:8px;font-size:14px;line-height:1.45;word-break:break-all;">
                      <a href="$eChat" style="color:#0f766e;font-weight:600;text-decoration:none;">$eChat</a>
                    </div>
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 18px 18px;">
                    <table role="presentation" cellspacing="0" cellpadding="0">
                      <tr>
                        <td style="border-radius:10px;background:#0f766e;">
                          <a href="$eChat" style="display:inline-block;padding:12px 18px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;">Open Chat on Phone</a>
                        </td>
                        <td style="width:10px;">&nbsp;</td>
                        <td style="border-radius:10px;background:#ffffff;border:1px solid #cbd5e1;">
                          <a href="$eHealth" style="display:inline-block;padding:12px 16px;font-size:14px;font-weight:600;color:#0f172a;text-decoration:none;">Check Health</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:22px;">
                <tr>
                  <td style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;font-weight:700;padding-bottom:8px;">Details</td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#64748b;width:34%;vertical-align:top;">Public URL</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;word-break:break-all;">
                    <a href="$ePublic" style="color:#0f766e;text-decoration:underline;">$ePublic</a>
                  </td>
                </tr>
                $prevRowHtml
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#64748b;vertical-align:top;">Local chat</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;word-break:break-all;">
                    <a href="$eLocal" style="color:#0f766e;text-decoration:underline;">$eLocal</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#64748b;vertical-align:top;">Machine</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#0f172a;">$eMachine</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#64748b;vertical-align:top;">Updated</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8ecef;font-size:13px;color:#0f172a;">$eWhenLocal<br><span style="color:#64748b;">$eWhenUtc</span></td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:22px;background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;">
                <tr>
                  <td style="padding:16px 18px;">
                    <div style="font-size:13px;font-weight:700;color:#9a3412;margin-bottom:8px;">Keep in mind</div>
                    <ul style="margin:0;padding-left:18px;color:#7c2d12;font-size:13px;line-height:1.55;">
                      <li>Quick-tunnel hostnames can change after reboot, crash, or tunnel restart.</li>
                      <li>The laptop must stay awake and online; sleep pauses access.</li>
                      <li>After shutdown, the next Windows logon starts services again and may issue a new URL.</li>
                    </ul>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:22px;">
                <tr>
                  <td align="center" style="padding-bottom:8px;">
                    <a href="$eChat" style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:12px 22px;border-radius:10px;">Launch AI Chat</a>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-bottom:6px;">
                    <a href="$ePublic" style="color:#0f766e;font-size:13px;text-decoration:underline;">Open public base URL</a>
                    &nbsp;&nbsp;|&nbsp;&nbsp;
                    <a href="$eHealth" style="color:#0f766e;font-size:13px;text-decoration:underline;">Service health</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:18px 28px 24px;border-top:1px solid #e8ecef;background:#f8fafc;">
              <div style="font-size:12px;color:#64748b;line-height:1.5;">
                Sent automatically by <strong style="color:#334155;">TaimoorKVD AI Assistant</strong> when tunnel configuration changes.<br>
                Source file on the laptop: <code style="font-size:11px;">data\logs\cloudflared-public-url.txt</code>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"@

$plainBody = @(
    $intro,
    "",
    "Open chat: $chatUrl",
    "Public URL: $PublicUrl",
    "Health: $healthUrl",
    "Local chat: $localChat",
    "Previous URL: $PreviousUrl",
    "Machine: $machine",
    "Updated: $whenLocal / $whenUtc",
    "",
    "Notes: laptop must stay awake/online; reboot may change the quick-tunnel URL.",
    "",
    "TaimoorKVD AI Assistant - Configuration Updates"
) -join "`r`n"

Write-Log "URL_EMAIL_START to=$to url=$PublicUrl"
try {
    $message = New-Object System.Net.Mail.MailMessage
    $message.From = New-Object System.Net.Mail.MailAddress($from, "TaimoorKVD AI Assistant")
    foreach ($addr in ($to -split ",")) {
        $trimmed = $addr.Trim()
        if ($trimmed) { [void]$message.To.Add($trimmed) }
    }
    $message.Subject = $subject
    $message.Body = $plainBody
    $message.IsBodyHtml = $false

    $htmlView = [System.Net.Mail.AlternateView]::CreateAlternateViewFromString(
        $htmlBody,
        [System.Text.Encoding]::UTF8,
        "text/html"
    )
    $textView = [System.Net.Mail.AlternateView]::CreateAlternateViewFromString(
        $plainBody,
        [System.Text.Encoding]::UTF8,
        "text/plain"
    )
    $message.AlternateViews.Add($textView)
    $message.AlternateViews.Add($htmlView)

    $client = New-Object System.Net.Mail.SmtpClient($hostName, $port)
    $client.EnableSsl = $true
    $client.Credentials = New-Object System.Net.NetworkCredential($user, $password)
    $client.Send($message)
    $htmlView.Dispose()
    $textView.Dispose()
    $message.Dispose()
    $client.Dispose()

    if (-not $Test) {
        [System.IO.File]::WriteAllText($LastEmailedFile, $PublicUrl)
    }
    Write-Log "URL_EMAIL_DONE to=$to"
    exit 0
} catch {
    Write-Log "URL_EMAIL_ERROR $($_.Exception.Message)"
    exit 1
}
