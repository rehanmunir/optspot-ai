#!/bin/sh
# Install the Agent Car Wash hooks into ~/.claude/settings.json so the car wash
# works in EVERY Claude Code session, not just this project.
#
# Safe by construction: backs up first, MERGES (never replaces), and skips any
# event where the car wash hook is already registered. Your existing hooks —
# including agent-office's — are preserved untouched. The two emitters are
# independent: each has its own marker file, so whichever server is running
# gets the events and the other one costs ~1 ms of nothing.
#
#   install:    ./scripts/install-global-hooks.sh
#   uninstall:  ./scripts/install-global-hooks.sh --remove
#   preview:    ./scripts/install-global-hooks.sh --dry-run

set -e
S="$HOME/.claude/settings.json"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
EMIT="\"$HERE/carwash-emit.sh\""
MODE="${1:-install}"

[ -f "$S" ] || { mkdir -p "$HOME/.claude"; echo '{}' > "$S"; }
BK="$S.bak-$(date +%Y%m%d-%H%M%S)"
cp "$S" "$BK"

/usr/bin/python3 - "$S" "$EMIT" "$MODE" <<'PY'
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
        if keep:
            h[ev] = keep
        elif ev in h:
            del h[ev]
    elif not has:
        h.setdefault(ev, []).append(entry(matcher))
        added += 1

if not h:
    s.pop("hooks", None)

if mode == "--dry-run":
    print(json.dumps(s, indent=4))
    print("\n[dry run] would add %d, remove %d — nothing written" % (added, removed), file=sys.stderr)
else:
    json.dump(s, open(path, "w"), indent=4)
    open(path, "a").write("\n")
    print("added %d, removed %d" % (added, removed), file=sys.stderr)

# report what survived, so the user can see their own hooks are intact
others = set()
for ev, arr in (s.get("hooks") or {}).items():
    for x in arr:
        for hk in x.get("hooks", []):
            c = hk.get("command", "")
            if emit not in json.dumps(c):
                others.add(c)
print("preserved non-carwash hooks: %s" % (sorted(others) or "none"), file=sys.stderr)
PY

if [ "$MODE" = "--dry-run" ]; then rm -f "$BK"; else echo "backup: $BK"; fi
