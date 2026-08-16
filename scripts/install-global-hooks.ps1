# Install the OPTSPOT AI hooks into %USERPROFILE%\.claude\settings.json so the
# wash works in EVERY Claude Code session on this Windows machine.
#
# Windows twin of install-global-hooks.sh: backs up first, MERGES (never
# replaces), skips events where the hook is already registered, and reports
# which non-carwash hooks survived. The JSON surgery is done by the same
# Python this app already requires for its server, because PowerShell's
# ConvertTo-Json mangles deep unknown structures.
#
#   install:    powershell -ExecutionPolicy Bypass -File scripts\install-global-hooks.ps1
#   uninstall:  ... -File scripts\install-global-hooks.ps1 -Remove
#   preview:    ... -File scripts\install-global-hooks.ps1 -DryRun

param(
    [switch]$Remove,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$emitPs1 = Join-Path $here 'carwash-emit.ps1'
$emitCmd = 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + $emitPs1 + '"'

$settings = Join-Path $env:USERPROFILE '.claude\settings.json'
if (-not (Test-Path -LiteralPath $settings)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $settings) | Out-Null
    Set-Content -LiteralPath $settings -Value '{}'
}
$backup = "$settings.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $settings -Destination $backup

$mode = if ($Remove) { '--remove' } elseif ($DryRun) { '--dry-run' } else { 'install' }

$py = @'
import json, sys, collections
path, emit, mode = sys.argv[1], sys.argv[2], sys.argv[3]
s = json.load(open(path), object_pairs_hook=collections.OrderedDict)
h = s.setdefault("hooks", collections.OrderedDict())
EVENTS = [("SessionStart", None), ("UserPromptSubmit", None), ("Stop", None),
          ("SubagentStart", "*"), ("SubagentStop", "*"),
          ("PreToolUse", "*"), ("PostToolUse", "*"), ("PostToolUseFailure", "*")]
def entry(matcher):
    e = collections.OrderedDict()
    if matcher is not None:
        e["matcher"] = matcher
    e["hooks"] = [collections.OrderedDict([("type", "command"), ("command", emit),
                                           ("async", True), ("timeout", 10)])]
    return e
added = removed = 0
for ev, matcher in EVENTS:
    arr = h.get(ev, [])
    has = any(emit in json.dumps(x) for x in arr)
    if mode == "--remove":
        keep = [x for x in arr if emit not in json.dumps(x)]
        removed += len(arr) - len(keep)
        if keep: h[ev] = keep
        elif ev in h: del h[ev]
    elif not has:
        h.setdefault(ev, []).append(entry(matcher))
        added += 1
if not h: s.pop("hooks", None)
if mode == "--dry-run":
    print(json.dumps(s, indent=4))
    print("[dry run] would add %d, remove %d - nothing written" % (added, removed), file=sys.stderr)
else:
    json.dump(s, open(path, "w"), indent=4)
    open(path, "a").write("\n")
    print("added %d, removed %d" % (added, removed), file=sys.stderr)
others = set()
for ev, arr in (s.get("hooks") or {}).items():
    for x in arr:
        for hk in x.get("hooks", []):
            c = hk.get("command", "")
            if emit not in json.dumps(c): others.add(c)
print("preserved non-carwash hooks: %s" % (sorted(others) or "none"), file=sys.stderr)
'@

$pyExe = $null
foreach ($cand in @('python', 'python3', 'py')) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) { $pyExe = $cand; break }
}
if (-not $pyExe) {
    Write-Error 'Python 3 is required (winget install Python.Python.3.12) - it also runs the OPTSPOT AI server.'
    exit 1
}

$tmp = New-TemporaryFile
Set-Content -LiteralPath $tmp -Value $py
try {
    & $pyExe $tmp $settings $emitCmd $mode
} finally {
    Remove-Item -LiteralPath $tmp -Force
}

if ($DryRun) { Remove-Item -LiteralPath $backup -Force }
else { Write-Host "backup: $backup" }
