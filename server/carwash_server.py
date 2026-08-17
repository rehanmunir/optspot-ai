#!/usr/bin/env python3
"""Agent Car Wash — live event bridge.

Hooks POST raw payloads here; the browser reads a redacted SSE stream. Python
3.9-compatible, stdlib only (/usr/bin/python3 on macOS is 3.9.6).

Three rules this file exists to enforce:
  1. Ingest never does socket I/O — a slow browser can never back-pressure a hook.
  2. Redaction happens BEFORE the ring buffer, so raw tool payloads can never be
     replayed to a later reconnect or surface in /state.
  3. Loopback + Host check + per-launch token. No CORS headers, ever.

The one write path besides ingest is /ask — the page's counter. It runs
`claude -p <prompt>` locally, as the user, and returns that job's reply to
the person who typed it. This does not weaken the redaction: the hook STREAM
stays redacted; the counter only ever returns the output of the order placed
through it. Same token gate as /close, one order at a time, hard timeout.

The server does NOT know what a "wash station" is. Deriving stations from tool
names is the viewer's job; keeping that out of here means this file stays a
dumb redacting pipe with one responsibility.
"""
from __future__ import annotations

import argparse, collections, hmac, itertools, json, os, queue, re, secrets
import shutil, signal, subprocess, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

MAX_BODY   = 1 << 20
RING       = 4096
HERE       = os.path.dirname(os.path.abspath(__file__))
# NOT CLAUDE_PLUGIN_DATA: that variable is shared by every plugin, so honouring
# it here would let the office and the car wash collide on one marker file and
# each send its hooks to the other's port.
DATA_DIR   = os.environ.get("AGENT_CARWASH_DATA") or os.path.expanduser("~/.claude/agent-carwash")
PROJECTS   = os.path.realpath(os.path.expanduser("~/.claude/projects"))
META_RE    = re.compile(r"^agent-[0-9a-f]{1,40}\.meta\.json$")
SUBCMD_OK  = {"git", "npm", "pnpm", "yarn", "cargo", "docker", "kubectl", "make",
              "python3", "python", "node", "pip", "brew", "go"}
# A basename is normally useful and harmless ("carwash_server.py"). A *secret*
# basename is not — "id_rsa" tells a shoulder-surfer more than we want to spend.
SECRET_HINT = re.compile(
    r"(^|/)\.(ssh|aws|gnupg|kube|docker|netrc)(/|$)|(^|/)\.env|id_rsa|id_ed25519|id_dsa"
    r"|credential|secret|passwd|password|\.pem$|\.key$|\.p12$|\.pfx$|\.keychain|token",
    re.I)
# `FOO=bar cmd ...` — the assignment is not the command, and its VALUE is
# exactly where people put secrets. Step over it rather than shipping it as
# the "first word".
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

_lock     = threading.Lock()
_buf      = collections.deque(maxlen=RING)
_seq      = itertools.count(1)
_clients  = set()
_actors   = {}                       # (session, actor) -> dict
_seen     = collections.OrderedDict()  # dedupe tool_use_id
_counters = {"in": 0, "bad": 0, "dropped": 0}
_last_evt = [time.time()]

TOKEN = secrets.token_hex(16)
PORT  = 0
ARGS  = None


# ── redaction ──────────────────────────────────────────────────────────────
def _clean(s, n=60):
    s = "".join(ch for ch in str(s or "") if 32 <= ord(ch) < 127)
    return s[:n]


def target_for(tool, ti):
    """Allowlist. Anything unmatched yields ''. The browser NEVER sees tool_input."""
    if not isinstance(ti, dict):
        return ""
    if tool in ("Read", "Edit", "Write", "NotebookEdit", "NotebookRead"):
        fp = ti.get("file_path") or ""
        if SECRET_HINT.search(fp):
            return "(private file)"
        return _clean(os.path.basename(fp))
    if tool in ("Bash", "BashOutput", "KillShell"):
        parts = (ti.get("command") or "").strip().split()
        while parts and ENV_ASSIGN.match(parts[0]):
            parts.pop(0)                     # `SECRET=xyz aws …` -> `aws`
        if not parts:
            return ""
        a0 = os.path.basename(parts[0])
        if SECRET_HINT.search(a0):           # a secret-shaped argv[0] is not a name
            return ""
        if a0 in SUBCMD_OK and len(parts) > 1 and parts[1].isalpha():
            return _clean(a0 + " " + parts[1])
        return _clean(a0)
    if tool in ("Grep", "Glob"):
        return "pattern (%d chars)" % len(ti.get("pattern") or ti.get("glob") or "")
    if tool == "WebFetch":
        try:
            return _clean(urlparse(ti.get("url") or "").hostname or "")
        except Exception:
            return ""
    if tool == "WebSearch":
        return "web search"
    if tool in ("Agent", "Task"):
        return _clean(ti.get("subagent_type") or "")
    if tool.startswith("mcp__"):
        seg = tool.split("__")
        return _clean(seg[1] if len(seg) > 1 else "")
    return ""


# ── label enrichment: SubagentStart carries no description ─────────────────
def meta_path(transcript_path, session_id, agent_id):
    name = "agent-%s.meta.json" % (agent_id or "")
    if not META_RE.match(name):
        return None
    try:
        p = os.path.dirname(os.path.abspath(transcript_path or ""))
    except Exception:
        return None
    for cand in (p, os.path.join(p, session_id or "", "subagents"),
                 os.path.join(os.path.dirname(p), "subagents")):
        f = os.path.realpath(os.path.join(cand, name))
        # containment check: transcript_path arrives over a socket
        if not f.startswith(PROJECTS + os.sep):
            continue
        if os.path.isfile(f) and os.path.getsize(f) < 64000:
            return f
    return None


def enrich(session, actor, transcript_path):
    """Retry ladder — never delay the spawn edge for a cosmetic string."""
    for delay in (0.0, 0.06, 0.15, 0.35, 0.7, 1.2):
        if delay:
            time.sleep(delay)
        f = meta_path(transcript_path, session, actor)
        if not f:
            continue
        try:
            with open(f) as fh:
                m = json.load(fh)
        except Exception:
            continue
        label = _clean(m.get("description") or "", 60)
        if label:
            emit("actor.updated", session, actor,
                 {"label": label, "depth": m.get("spawnDepth", 1)})
            return


# ── event bus ──────────────────────────────────────────────────────────────
def emit(t, session, actor, d):
    with _lock:
        ev = {"v": 1, "seq": next(_seq), "ts": round(time.time(), 3),
              "t": t, "s": session or "", "a": actor or "main", "d": d}
        _buf.append(ev)
        _last_evt[0] = ev["ts"]
        dead = []
        for q in _clients:
            try:
                q.put_nowait(ev)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _clients.discard(q)
            _counters["dropped"] += 1
        return ev


def snapshot_locked(resync=False):
    actors = []
    for (s, a), rec in _actors.items():
        if rec.get("stopped"):
            continue
        actors.append({"id": a, "kind": rec["kind"], "agent_type": rec.get("agent_type", ""),
                       "label": rec.get("label", ""), "spawned_at": rec.get("spawned_at", 0),
                       "live": [{"id": k, "tool": v[0], "target": v[1], "started_at": v[2]}
                                for k, v in rec.get("live", {}).items()]})
    return {"v": 1, "seq": next(_seq), "ts": round(time.time(), 3), "t": "wash.snapshot",
            "s": "", "a": "main",
            "d": {"actors": actors, "resync": bool(resync), "counters": dict(_counters)}}


def ensure_actor(session, actor, kind, agent_type="", label=""):
    """Materialise an actor the browser has not been told about yet."""
    key = (session, actor)
    with _lock:
        known = key in _actors
        if not known:
            _actors[key] = {"kind": kind, "agent_type": agent_type, "label": label,
                            "spawned_at": round(time.time(), 3), "live": {}}
    if not known:
        emit("actor.spawned", session, actor,
             {"kind": kind, "agent_type": agent_type,
              "label": label or agent_type or ("session " + (session or "")[:6]),
              "pending_label": not label})
    return _actors[key]


# ── hook payload -> car wash events ────────────────────────────────────────
def translate(p):
    ev      = p.get("hook_event_name") or ""
    session = p.get("session_id") or ""
    agent   = p.get("agent_id")
    actor   = agent or "main"
    tpath   = p.get("transcript_path") or ""
    _counters["in"] += 1

    # The main session is never announced by any hook — synthesise it so the
    # browser never sees an event for an actor it does not know.
    # cwd basename and agent_type arrive over a socket: _clean() them like
    # every other derived string, or they are the only ones that skip it.
    if not agent:
        ensure_actor(session, "main", "main", "",
                     _clean(os.path.basename(p.get("cwd") or "")) or "main")

    if ev == "SubagentStart":
        rec = ensure_actor(session, actor, "subagent", _clean(p.get("agent_type") or "", 40))
        threading.Thread(target=enrich, args=(session, actor, tpath), daemon=True).start()
        return

    if ev == "SubagentStop":
        with _lock:
            rec = _actors.get((session, actor))
            live = list(rec["live"].items()) if rec else []
            if rec:
                rec["live"] = {}
                rec["stopped"] = True
        for tid, v in live:                      # never leave a jet running
            emit("tool.finished", session, actor,
                 {"id": tid, "tool": v[0], "ok": True, "ms": 0, "orphaned": True})
        emit("actor.stopped", session, actor, {})
        return

    if ev == "PreToolUse":
        tool = p.get("tool_name") or "?"
        tid  = p.get("tool_use_id") or ""
        key  = session + "|" + tid
        with _lock:
            if tid and key in _seen:
                return                            # duplicate: liveN is a counter
            if tid:
                _seen[key] = 1
                if len(_seen) > 4000:
                    _seen.popitem(last=False)
        rec = ensure_actor(session, actor, "subagent" if agent else "main",
                           _clean(p.get("agent_type") or "", 40))
        tgt = target_for(tool, p.get("tool_input"))
        # `Agent` never emits PostToolUse (verified) — its terminal is
        # SubagentStop, so it must not open a jet that nothing will close.
        if tool not in ("Agent", "Task"):
            with _lock:
                rec["live"][tid] = (tool, tgt, round(time.time(), 3))
        emit("tool.started", session, actor,
             {"id": tid, "tool": _clean(tool, 40), "target": tgt,
              "spawns": tool in ("Agent", "Task")})
        return

    if ev in ("PostToolUse", "PostToolUseFailure"):
        tool = p.get("tool_name") or "?"
        tid  = p.get("tool_use_id") or ""
        ok   = ev == "PostToolUse"
        with _lock:
            rec = _actors.get((session, actor))
            if rec:
                rec["live"].pop(tid, None)
        emit("tool.finished" if ok else "tool.failed", session, actor,
             {"id": tid, "tool": _clean(tool, 40), "ok": ok,
              "ms": int(p.get("duration_ms") or 0)})       # harness already timed it
        return

    if ev == "UserPromptSubmit":
        # A car arrives at the gate. Length only — never the prompt text.
        emit("prompt.submitted", session, "main",
             {"chars": len(p.get("user_prompt") or "")})
        return

    if ev == "Stop":
        if agent:
            return                                # Stop inside a subagent: ignore
        emit("turn.ended", session, "main", {})   # the car may leave, and only now
        return

    if ev == "SessionStart":
        emit("session.started", session, "main",
             {"cwd_name": _clean(os.path.basename(p.get("cwd") or ""))})
        return


# ── the counter ────────────────────────────────────────────────────────────
_ask_busy = threading.Lock()


def run_claude(prompt):
    exe = shutil.which("claude")
    if not exe:
        return (False, "the `claude` CLI is not on PATH for the wash server")
    # A fresh-terminal environment. The wash server is often launched from
    # inside a Claude session, and any inherited CLAUDE_* state makes the
    # child CLI think it is nested — or, worse, differently authenticated
    # ("Not logged in" with a perfectly logged-in user).
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    try:
        r = subprocess.run([exe, "-p", prompt],
                           capture_output=True, text=True, timeout=300,
                           cwd=os.path.expanduser("~"), env=env)
    except subprocess.TimeoutExpired:
        return (False, "timed out after five minutes")
    except Exception as e:
        return (False, "could not run claude: %s" % e)
    if r.returncode != 0:
        blurb = (r.stderr or r.stdout or "claude exited %d" % r.returncode)
        if "Not logged in" in blurb:
            # The standalone CLI keeps its own login, separate from the
            # desktop app's. Say so, or this reads like a wash bug.
            blurb = ("the local `claude` CLI is not logged in - its login is "
                     "separate from the Claude desktop app's. Open a terminal, "
                     "run `claude`, complete /login once (and `claude update` "
                     "if it is old), then order again.")
        return (False, blurb[-4000:])
    return (True, (r.stdout or "").strip()[:100000])


# ── http ───────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _host_ok(self):
        h = (self.headers.get("Host") or "").strip()
        return h in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)

    def _tok(self, t):
        return hmac.compare_digest(t, TOKEN)

    def _deny(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    # self.path carries the query string; every route below matches on the
    # path alone, or `?debug=1` and friends would 404.
    def _path(self):
        return urlparse(self.path).path

    def do_POST(self):
        if not self._host_ok():
            return self._deny()
        m = re.match(r"^/ingest/([0-9a-f]{32})$", self._path())
        if m and self._tok(m.group(1)):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                _counters["bad"] += 1
                return self._send(b"", "text/plain", 413)
            raw = self.rfile.read(n) if n else b"{}"
            self._send(b"{}", "application/json")      # reply first, then book-keep
            try:
                p = json.loads(raw)
                if not isinstance(p, dict):
                    raise ValueError
            except Exception:
                _counters["bad"] += 1
                return
            try:
                translate(p)
            except Exception:
                _counters["bad"] += 1                  # a bad event must not kill the server
            return
        m = re.match(r"^/c/([0-9a-f]{32})/ask$", self._path())
        if m and self._tok(m.group(1)):
            return self._ask()
        m = re.match(r"^/c/([0-9a-f]{32})/close$", self._path())
        if m and self._tok(m.group(1)):
            self._send(b"closing")
            threading.Thread(target=self._bye, daemon=True).start()
            return
        return self._deny()

    def _ask(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 8192:
            return self._send(b'{"ok":false,"text":"prompt too long"}', "application/json", 413)
        try:
            body = json.loads(self.rfile.read(n) if n else b"{}")
            prompt = str(body.get("prompt") or "").strip()
        except Exception:
            prompt = ""
        if not prompt or len(prompt) > 4000:
            return self._send(b'{"ok":false,"text":"empty or oversized prompt"}',
                              "application/json", 400)
        if not _ask_busy.acquire(blocking=False):
            return self._send(b'{"ok":false,"text":"the counter is busy - one order at a time"}',
                              "application/json", 409)
        try:
            ok, text = run_claude(prompt)
        finally:
            _ask_busy.release()
        # the reply goes back over the same tokenised loopback socket it was
        # ordered on, and is never buffered, logged, or written anywhere
        self._send(json.dumps({"ok": ok, "text": text}).encode(), "application/json")

    def _bye(self):
        time.sleep(0.2)
        shutdown()

    def do_GET(self):
        if not self._host_ok():
            return self._deny()
        m = re.match(r"^/c/([0-9a-f]{32})(/.*)?$", self._path())
        if not m or not self._tok(m.group(1)):
            return self._deny()
        rest = m.group(2) or "/"
        if rest == "/":
            return self._page()
        if rest == "/stream":
            return self._stream()
        if rest == "/state":
            with _lock:
                s = snapshot_locked()
            return self._send(json.dumps(s, indent=1).encode(), "application/json")
        return self._deny()

    def _page(self):
        try:
            with open(ARGS.viewer, "rb") as f:
                html = f.read()
        except OSError:
            return self._send(b"viewer not found", "text/plain", 500)
        inject = ('<script>window.__CW_LIVE={stream:"/c/%s/stream",close:"/c/%s/close",'
                  'ask:"/c/%s/ask"};</script>' % (TOKEN, TOKEN, TOKEN)).encode()
        # Inject before the LAST closing body tag, not the first. Injecting at
        # the first one puts the token script inside whatever came before it —
        # and if that is the viewer's own <script>, the browser terminates the
        # script element at the injected "</scr"+"ipt>" and silently drops the
        # rest of the viewer. A closing-body string can legitimately appear in
        # a comment or a template literal; the real document end cannot.
        i = html.rfind(b"</body>")
        html = (html[:i] + inject + html[i:]) if i >= 0 else (html + inject)
        self._send(html)

    def _stream(self):
        last = self.headers.get("Last-Event-ID")
        self.send_response(200)
        for k, v in (("Content-Type", "text/event-stream; charset=utf-8"),
                     ("Cache-Control", "no-store"),
                     ("Connection", "keep-alive"),
                     ("X-Accel-Buffering", "no"),
                     ("X-Content-Type-Options", "nosniff")):
            self.send_header(k, v)
        self.end_headers()

        q = queue.Queue(maxsize=1000)
        with _lock:
            if last and last.isdigit() and _buf and _buf[0]["seq"] <= int(last) + 1:
                backlog = [e for e in _buf if e["seq"] > int(last)]     # clean resume
            else:
                backlog = [snapshot_locked(resync=bool(last))]          # cold or past horizon
            _clients.add(q)
        try:
            self.wfile.write(b"retry: 1500\n\n")
            self.wfile.flush()
            for e in backlog:
                self._frame(e)
            while True:
                try:
                    self._frame(q.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            with _lock:
                _clients.discard(q)

    def _frame(self, e):
        self.wfile.write(("id: %d\ndata: %s\n\n"
                          % (e["seq"], json.dumps(e, separators=(",", ":")))).encode())
        self.wfile.flush()

    def log_message(self, *a):
        pass                                        # no request log, ever


class CarWash(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


SRV = None


def write_markers(url_ingest, url_page):
    # These two files carry the token that guards the stream, so they are the
    # user's alone — 0700 on the directory, 0600 on the files. Default umask
    # would leave them world-readable, and any local process could then read
    # the whole feed.
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    live = os.path.join(DATA_DIR, "carwash.live")
    meta = os.path.join(DATA_DIR, "carwash.json")
    for p in (live, meta):                          # own them before writing
        try:
            os.close(os.open(p, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600))
            os.chmod(p, 0o600)
        except OSError:
            pass
    with open(live, "w") as f:
        f.write(url_ingest + "\n")                  # one line: the hook's read is a builtin
    with open(meta, "w") as f:
        json.dump({"pid": os.getpid(), "port": PORT, "token": TOKEN,
                   "url": url_page, "viewer": ARGS.viewer,
                   "claude_pid": os.environ.get("CLAUDE_PID"),
                   "started": time.time()}, f, indent=1)


def clear_markers():
    for n in ("carwash.live", "carwash.json"):
        try:
            os.remove(os.path.join(DATA_DIR, n))
        except OSError:
            pass


def shutdown(*a):
    emit("wash.closing", "", "main", {"reason": "shutdown"})
    clear_markers()
    if SRV:
        threading.Thread(target=SRV.shutdown, daemon=True).start()
    time.sleep(0.3)
    os._exit(0)


def watchdog():
    """SessionEnd only gets ~1.5 s, so shutdown is inferred instead."""
    cpid = os.environ.get("CLAUDE_PID")
    # On Windows os.kill(pid, 0) is NOT a probe: any signal other than the two
    # CTRL events unconditionally TerminateProcess()es the target. Probing
    # would kill the very Claude process we are watching, so rely on the idle
    # timeout there instead.
    if os.name == "nt":
        cpid = None
    gone_since = None
    while True:
        time.sleep(5)
        if ARGS.idle and time.time() - _last_evt[0] > ARGS.idle and not _clients:
            return shutdown()
        if not cpid:
            continue
        try:
            os.kill(int(cpid), 0)
            gone_since = None
        except Exception:
            gone_since = gone_since or time.time()
            if time.time() - gone_since > 60 and not _clients:
                return shutdown()


def main():
    global PORT, SRV, ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--viewer", default=os.path.join(HERE, "..", "ui", "index.html"))
    ap.add_argument("--port", type=int, default=47318)   # office holds 47317
    ap.add_argument("--idle", type=int, default=900)
    ap.add_argument("--no-browser", action="store_true")
    ARGS = ap.parse_args()
    ARGS.viewer = os.path.abspath(ARGS.viewer)

    try:
        SRV = CarWash(("127.0.0.1", ARGS.port), Handler)
    except OSError:
        SRV = CarWash(("127.0.0.1", 0), Handler)    # never kill a stranger's process
    PORT = SRV.server_address[1]

    page   = "http://127.0.0.1:%d/c/%s/" % (PORT, TOKEN)
    ingest = "http://127.0.0.1:%d/ingest/%s" % (PORT, TOKEN)
    write_markers(ingest, page)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    threading.Thread(target=watchdog, daemon=True).start()

    print(page, flush=True)
    if not ARGS.no_browser:
        try:
            webbrowser.open(page)
        except Exception:
            pass
    try:
        SRV.serve_forever()
    finally:
        clear_markers()


if __name__ == "__main__":
    main()
