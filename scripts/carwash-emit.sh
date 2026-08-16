#!/bin/sh
# Agent Car Wash event emitter.
#
# Runs async, so it is never in the user's critical path. Three hard rules:
#   - always exit 0 (a visualization must never be able to colour a hook red)
#   - never write to stdout (async hook stdout is parsed as JSON)
#   - cost ~nothing when the car wash is closed
#
# The marker gate is what makes "closed" cheap — without it every hook pays for
# a doomed TCP connect. Note the marker directory is car-wash-specific and does
# NOT honour CLAUDE_PLUGIN_DATA: that variable is shared by every plugin, and
# honouring it would let this emitter post into agent-office's port.
trap '' PIPE

M="${AGENT_CARWASH_DATA:-$HOME/.claude/agent-carwash}/carwash.live"

# Closed: drain stdin with a shell builtin (no fork) so the writer never sees
# EPIPE, then leave.
if [ ! -f "$M" ]; then
  IFS= read -r _ 2>/dev/null
  exit 0
fi

IFS= read -r URL < "$M" 2>/dev/null || exit 0
[ -n "$URL" ] || exit 0

# Refuse to send anywhere but our own loopback port, even if the marker is
# tampered with.
case "$URL" in
  http://127.0.0.1:*) ;;
  *) IFS= read -r _ 2>/dev/null; exit 0 ;;
esac

if [ "${AGENT_CARWASH_DEBUG:-0}" = "1" ]; then
  ERR="${AGENT_CARWASH_DATA:-$HOME/.claude/agent-carwash}/emit.err"
else
  ERR=/dev/null
fi

# --noproxy '*' is mandatory: without it a configured http_proxy would receive
# every payload. -4 skips a pointless ::1 attempt.
/usr/bin/curl -s -4 --noproxy '*' --connect-timeout 1 -m 2 \
  -o /dev/null -X POST -H 'Content-Type: application/json' \
  --data-binary @- "$URL" >/dev/null 2>>"$ERR"

exit 0
