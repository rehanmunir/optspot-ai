#!/usr/bin/env python3
"""Assert that nothing sensitive can reach the browser.

Injects deliberately hostile hook payloads through the REAL ingest endpoint,
then reads back every channel the browser can actually reach — the SSE stream
and /state — and fails if any secret survives anywhere in either.

This is the check that makes the privacy claim in the README a fact rather than
an intention. Run it against a live server:

    ./scripts/assert_redaction.py
"""
from __future__ import annotations

import json, os, sys, threading, time
import urllib.request

DATA = os.environ.get("AGENT_CARWASH_DATA") or os.path.expanduser("~/.claude/agent-carwash")

# Ingest de-duplicates on (session, tool_use_id) so a replayed call cannot
# strand a jet. With fixed ids this assertion quietly stopped injecting
# anything on its second run and "passed" vacuously, so every run gets its own
# session and ids. A test that degrades to trivially-true is worse than none.
RUN = "redact-%d" % (time.time() * 1000)

SECRETS = [
    "/etc/passwd", "--porcelain", "--untracked=all",     # command line
    "id_rsa", "BEGIN RSA PRIVATE KEY",                   # key material
    "AWS_SECRET_ACCESS_KEY",                             # the search pattern
    "SUPERSECRET", "api.internal.example.com/v1/keys",   # url query + path
    "hunter2",                                           # prompt text
    "the answer is 42",                                  # an agent's own output
    "wJalrXUtnFEMIsecret",                               # a secret in `VAR=… cmd`
]

PAYLOADS = [
    {"hook_event_name": "SessionStart", "session_id": RUN, "cwd": "/tmp/redact"},
    {"hook_event_name": "UserPromptSubmit", "session_id": RUN,
     "user_prompt": "my password is hunter2 please remember it"},
    {"hook_event_name": "PreToolUse", "session_id": RUN, "tool_name": "Bash",
     "tool_use_id": RUN + "-1",
     "tool_input": {"command": "git status --porcelain --untracked=all /etc/passwd"}},
    {"hook_event_name": "PreToolUse", "session_id": RUN, "tool_name": "Read",
     "tool_use_id": RUN + "-2", "tool_input": {"file_path": "/Users/x/.ssh/id_rsa"}},
    # people put secrets in leading env assignments; the "first word" rule
    # used to ship them verbatim
    {"hook_event_name": "PreToolUse", "session_id": RUN, "tool_name": "Bash",
     "tool_use_id": RUN + "-5",
     "tool_input": {"command": "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIsecret aws s3 ls"}},
    {"hook_event_name": "PreToolUse", "session_id": RUN, "tool_name": "Grep",
     "tool_use_id": RUN + "-3", "tool_input": {"pattern": "AWS_SECRET_ACCESS_KEY"}},
    {"hook_event_name": "PreToolUse", "session_id": RUN, "tool_name": "WebFetch",
     "tool_use_id": RUN + "-4",
     "tool_input": {"url": "https://api.internal.example.com/v1/keys?token=SUPERSECRET"}},
    {"hook_event_name": "PostToolUse", "session_id": RUN, "tool_name": "Read",
     "tool_use_id": RUN + "-2", "duration_ms": 12,
     "tool_response": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKC\n"},
    {"hook_event_name": "SubagentStop", "session_id": RUN, "agent_id": "deadbeef",
     "final_message": "the answer is 42"},
]


def main():
    try:
        meta = json.load(open(os.path.join(DATA, "carwash.json")))
    except OSError:
        sys.exit("no live car wash — start server/carwash_server.py first")
    base, token = "http://127.0.0.1:%d" % meta["port"], meta["token"]

    seen = []                                    # every byte the browser receives

    def listen():
        try:
            r = urllib.request.urlopen(base + "/c/%s/stream" % token, timeout=8)
            end = time.time() + 6
            while time.time() < end:
                line = r.readline()
                if not line:
                    break
                seen.append(line.decode("utf-8", "replace"))
        except Exception:
            pass

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.6)                              # let the stream attach

    for p in PAYLOADS:
        req = urllib.request.Request(base + "/ingest/" + token,
                                     data=json.dumps(p).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
        time.sleep(0.05)

    time.sleep(1.2)
    state = urllib.request.urlopen(base + "/c/%s/state" % token, timeout=3).read().decode()
    t.join(timeout=8)
    stream = "".join(seen)

    print("captured %d bytes of stream, %d bytes of /state" % (len(stream), len(state)))
    bad = []
    for s in SECRETS:
        for name, blob in (("stream", stream), ("/state", state)):
            if s in blob:
                bad.append("%s leaked into %s" % (s, name))

    # and prove the useful, harmless derivations DID survive
    kept = [k for k in ("git status", "(private file)", "pattern (21 chars)",
                        "api.internal.example.com", "aws") if k in stream]

    if bad:
        print("\nFAIL")
        for b in bad:
            print("  ✗ " + b)
        sys.exit(1)
    expect = ("git status", "(private file)", "pattern (21 chars)",
              "api.internal.example.com", "aws")
    missing = [k for k in expect if k not in kept]
    if missing:
        # Nothing leaked, but nothing arrived either — the run proved nothing.
        print("\nINCONCLUSIVE — these derived values never appeared: "
              + ", ".join(missing))
        print("the payloads were probably de-duplicated; the assertion did not "
              "actually exercise redaction")
        sys.exit(2)
    print("\nPASS — none of the %d secrets reached the browser" % len(SECRETS))
    print("kept (derived, harmless): " + ", ".join(kept))


if __name__ == "__main__":
    main()
