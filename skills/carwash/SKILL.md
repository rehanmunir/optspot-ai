---
name: carwash
description: Open OPTSPOT AI (the Agent Car Wash) — a live view of Claude's own agents and tool calls as a car wash, where a task is a car and the agents are washing it. Use when the user says "open the car wash", "open the carwash", "open optspot", "open optspot ai", "wash my tasks", "show me the agents washing", "start the carwash visualizer", or asks to close/stop the car wash.
argument-hint: "[close]"
---

# OPTSPOT AI (Agent Car Wash)

A local, loopback-only server receives hook events and serves a browser view of
them. When the server is not running the hooks cost ~1 ms of background work
each and do nothing.

This is a sibling of `agent-office` and is deliberately independent: its own
port, its own marker directory, its own hooks. Both can be installed, and both
can even run at once.

## Open it

1. **Is one already open?** Read `~/.claude/agent-carwash/carwash.json`.
   - Present → check the pid is alive: `kill -0 <pid> 2>/dev/null && echo alive`.
     If alive, do **not** start a second server — open the `url` from that file
     and stop here.
   - Absent or the pid is dead → continue.

2. **Start it**, in the background, never in the foreground. The server ships
   inside this plugin: from this SKILL.md, the plugin root is two directories
   up, and the server is `<plugin-root>/server/carwash_server.py`:

   ```
   python3 "<plugin-root>/server/carwash_server.py" --no-browser
   ```

   Use `run_in_background: true`. Poll for `~/.claude/agent-carwash/carwash.json`
   (up to ~5 s) and read `url` from it. **Never assume the port** — on a
   conflict the server binds an OS-assigned one rather than killing whatever
   holds 47318.

3. **Show it.** Open the url in the Browser pane with `preview_start({url})`.
   Then tell the user the url in one line, and that they can say "close the car
   wash" to stop it.

## Close it

Read `url` from `carwash.json` and `POST` to it with `close` appended:

```
curl -s -X POST "<url>close"
```

If that fails, `kill <pid>` from the same file. Either way the server removes
its marker on exit, which returns the hooks to the fast path.

## How to read it

- A **car** is one tool call: it enters when the call starts, washes at its
  family's stage while the call runs, and leaves clean only when it completes.
  A failed call skips the towel and leaves dirty. Parallel calls are several
  cars in the tunnel at once.
- The **ticket** is the turn: Josh opens it at your prompt, Levi closes it at
  turn end, and the closed ticket shows washed/failed counts.
- A **washer** is one agent. Every subagent takes a **detail bay** and washes
  its own delegated task.
- **Jets running** means a real tool call is in flight. That is the whole truth
  channel; nothing else lights them.
- Stages: WATER POUR (read/search), SOAP & FOAM (write/edit), ROLLERS
  (bash/MCP), AIR DRY (the ride out after a call really completes). Jeremy
  towels each finished car; Levi sees every car off.
- Spawning agents, checklist tools (TodoWrite/Skill) and AskUserQuestion light an **add-on service** instead of
  moving the car, because they are real work that says nothing about which
  stage the turn is in.
- There is **no percentage and no progress bar**: the hook stream cannot know
  how much of a turn remains. A car comes clean only when its own call really
  completes, and a ticket only closes when the turn really ends.

## If nothing moves

Hooks are plugin-managed (`hooks/hooks.json`) and fire in sessions started
after the plugin was installed. If the wash is connected (the header says
`● live`) but stays empty, the hooks are not firing — check with
`claude --debug`, or set `AGENT_CARWASH_DEBUG=1` and read
`~/.claude/agent-carwash/emit.err`.

An empty forecourt with `● live` is also simply correct when Claude is idle.
The wash does not invent traffic.

## What the page can see

Say this plainly if asked. The browser receives tool **names** and short derived
labels only:

- a file's **basename** (`index.html`), or `(private file)` for anything under
  `.ssh`/`.env`/`.aws` or matching key/secret/token patterns
- a command's **first word**, plus the subcommand for a small allowlist
  (`git status` — never the flags or paths)
- a URL's **hostname** only
- `pattern (21 chars)` for a search — never the pattern itself
- an MCP tool's **server** segment only

It never receives file contents, command lines, tool outputs, search patterns,
prompt text, or an agent's final message. Redaction happens at ingest, before
anything is buffered, so raw payloads cannot be replayed to a later reconnect.

The server binds `127.0.0.1` only, validates the `Host` header, sends no CORS
headers, and puts a fresh 128-bit token in every URL path.
