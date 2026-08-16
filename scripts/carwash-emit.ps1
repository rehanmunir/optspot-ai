# OPTSPOT AI hook emitter — Windows twin of carwash-emit.sh.
#
# Same three hard rules:
#   - always exit 0 (a visualization must never be able to colour a hook red)
#   - never write to stdout (async hook stdout is parsed as JSON)
#   - cost ~nothing when the wash is closed (the marker gate)
#
# PowerShell 5.1-compatible. Uses Invoke-RestMethod so there is no dependency
# on curl.exe; the loopback-only check mirrors the sh emitter exactly.
#
# Register in %USERPROFILE%\.claude\settings.json as, e.g.:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\carwash-emit.ps1"
# (or run scripts\install-global-hooks.ps1, which does it for you)

$ErrorActionPreference = 'SilentlyContinue'

$dataDir = if ($env:AGENT_CARWASH_DATA) { $env:AGENT_CARWASH_DATA }
           else { Join-Path $env:USERPROFILE '.claude\agent-carwash' }
$marker = Join-Path $dataDir 'carwash.live'

# Drain stdin regardless — the writer must never see a broken pipe.
$payload = [Console]::In.ReadToEnd()

if (-not (Test-Path -LiteralPath $marker)) { exit 0 }

$url = Get-Content -LiteralPath $marker -TotalCount 1
if (-not $url) { exit 0 }

# Refuse to send anywhere but our own loopback port, even if the marker is
# tampered with.
if (-not $url.StartsWith('http://127.0.0.1:')) { exit 0 }

try {
    Invoke-RestMethod -Uri $url -Method Post -Body $payload `
        -ContentType 'application/json' -TimeoutSec 2 | Out-Null
} catch { }

exit 0
