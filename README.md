# OPTSPOT AI

*(project folder: `agent-carwash`)*

A car wash where every car is a real task, every washer is a real Claude Code
agent, and the jets run **if and only if** a real tool call is in flight.
The wash is branded **OPTSPOT AI**; everything below is how it stays honest.

```
Claude Code ──hooks (async, never blocking)──► carwash-emit.sh ──curl──► carwash_server.py
   SubagentStart/Stop · Pre/PostToolUse         ~1 ms when the            redact at ingest
   PostToolUseFailure · Stop · SessionStart      wash is closed           ring + SSE
   UserPromptSubmit                                                              │
                                                                     SSE (id: = seq)
                                                                                 ▼
                                                            ui/index.html — 2D SVG car wash
                                                                                 │
                                                            desktop/ — Tauri shell, same page
```

Sibling of `agent-office`, deliberately independent: its own port, marker
directory and hooks. Both can be installed, and both can run at once.

## Run it

```bash
"agent-carwash/server/carwash_server.py"
```

It prints a URL and opens a browser (`--no-browser` to skip). Or ask Claude:
*"open the car wash"* — see `skills/carwash/SKILL.md`.

Close it by POSTing to `<url>close`, or `kill` the pid in
`~/.claude/agent-carwash/carwash.json`. The server removes its marker on exit,
which returns the hooks to the fast path.

## Install as a Claude Code plugin

The repo is its own plugin marketplace, and the plugin carries the hooks —
no manual `settings.json` surgery, and it covers **every** project:

```bash
claude plugin marketplace add "/path/to/agent-carwash"   # or the GitHub repo, once pushed
claude plugin install agent-carwash@optspot
```

That registers all eight hooks via `hooks/hooks.json`
(`${CLAUDE_PLUGIN_ROOT}/scripts/carwash-emit.sh`) and ships the skill, so
*"open the car wash"* / *"open optspot"* works in any session. Uninstall with
`claude plugin disable agent-carwash` or remove the marketplace. If you had
the hooks registered project-scoped or via `install-global-hooks.sh`, remove
those after installing the plugin — two registrations mean duplicate
`PostToolUse` events, which double-count the stage timers. (Windows: plugin
hooks run the sh emitter; on native-Windows Claude Code use
`scripts\install-global-hooks.ps1` instead of the plugin's hooks.)

## The desktop app (macOS + Windows)

`desktop/` is a Tauri 2 shell around the same loopback page — no second
viewer, no bundled web assets beyond what the server already serves. It
attaches to a running wash if one exists (and will not kill a server it only
attached to); otherwise it spawns the bundled server and, on quit, closes it
**gracefully** through its own `/close` endpoint so the marker files are
removed — a hard kill would leave every later hook paying for a doomed
connect.

**macOS** — build locally:

```bash
cd agent-carwash/desktop && npm ci && npx tauri build
```

Products land in `desktop/src-tauri/target/release/bundle/`: `OPTSPOT AI.app`
and a `.dmg`. The bundle is ad-hoc signed (no Developer ID), so the first
launch needs right-click → Open past Gatekeeper.

**Windows** — a Windows installer cannot be cross-compiled from macOS (MSVC +
NSIS exist only on Windows), so it comes from CI:
`.github/workflows/build.yml` builds macOS (Apple Silicon + Intel) and a
Windows x64 NSIS `.exe` + `.msi` on every `v*` tag — push this repo to GitHub
and tag it, then collect the draft release. On the machine itself:

1. Install Python 3 (`winget install Python.Python.3.12`) — it runs the
   bundled server; the app tries `python`, `python3`, then `py -3` and says
   exactly this if none work.
2. Run `scripts\install-global-hooks.ps1` once (backs up and MERGES
   `%USERPROFILE%\.claude\settings.json`; `-Remove` uninstalls) — it registers
   `scripts\carwash-emit.ps1`, the PowerShell twin of the sh emitter, with the
   same loopback-only guard.
3. Launch OPTSPOT AI. WebView2 is preinstalled on Windows 10/11; the NSIS
   installer fetches it if missing.

Windows honesty note: the server skips the CLAUDE_PID liveness probe there,
because on Windows `os.kill(pid, 0)` is not a probe — it *terminates* the
target. The idle timeout covers shutdown instead.

## The metaphor, which is load-bearing rather than decorative

| on screen | what it actually is |
|---|---|
| a **car** | one turn — your prompt in, Claude's turn ended |
| a **washer** | one agent |
| the **tunnel** | main Claude's work on your turn |
| a **detail bay** | one subagent, washing its own delegated task |
| **jets running** | a real tool call is in flight — the whole truth channel |
| an **add-on service** | a real tool that is not a wash step (`Agent`, `AskUserQuestion`) |

### The four phases of a turn, and who is on each

The tunnel is only the middle of the story. A turn also has a beginning —
Claude reading the job before it touches a single tool — and an end, where the
work is finished off and the results handed back. Each phase has one member of
staff, and each is entered on a real signal.

| phase | staff | entered when |
|---|---|---|
| **CHECK-IN** | **Josh** | a prompt is open and **no tool has run yet** — the welcome |
| **THE TUNNEL** | **Nick** | a tool call is in flight — the four stages |
| **TOWEL & INTERIOR** | **Jeremy** | `turn.ended` fired — towel dry, vacuum the inside |
| **GOODBYE** | **Levi** | the ticket is read back, then the clean car leaves |

**Thinking is evidenced, not guessed.** It is the exact complement of "a call is
in flight" inside an open turn, so Josh checking the car in is a real state and
so is the pause mid-tunnel — the thought bubble says *no call in flight*, never
what Claude is thinking about, because the stream cannot know and does not
receive it.

Josh and Nick are driven purely by events. Jeremy and Levi run on a short timer,
and those are the **only** timed moves on the page — an outro for something that
genuinely happened, never a claim about work still in progress.

Levi's goodbye is deliberately thin: the viewer never receives Claude's reply,
so the ticket he hands back contains only measured facts — calls completed,
touch-ups, elapsed time.

### The four stages

The tunnel runs the four stages a real wash has, and each is entered on
evidence, never on a timer. The stream's tool families group naturally onto
them:

| # | stage | the machinery | the evidence |
|---|---|---|---|
| 1 | WATER POUR | overhead pipe, four pouring nozzles | `Read` `Grep` `Glob` `WebFetch` `WebSearch` … — soaking the task |
| 2 | SOAP & FOAM | three coloured foam cannons | `Write` `Edit` `NotebookEdit` — laying the new material on |
| 3 | ROLLERS | two striped side brushes + a top roller | `Bash` `mcp__*` — scrubbing it all over |
| 4 | AIR DRY | blower bank, air streaks | the exit ride — fired by `turn.ended` and nothing else |

**The conveyor never runs backwards.** A real tunnel is a chain: forward or
hold, never reverse. So the car's position is the furthest stage evidenced
this turn — still advanced only by real calls, never by time. When an
earlier-family call runs after the car has moved on, that stage's lamp lights
and its washer takes the work **to the car**: a touch-up crew, like the
hand-prep attendants in a real wash, counted on the ticket as *touch-ups*.
And the machinery is sensor-driven like the real thing — an arch runs only
with the car under it, so a touch-up shows hand tools at the bodywork, not a
station spraying at nothing.

Plan and wrap-up tools (`TodoWrite` `Skill` `ExitPlanMode` …) are checklist
work, which happens beside the tunnel — the CHECKLIST add-on, not a stage.

The car visibly changes as the stages really run: a wet sheen under the water,
clinging foam under the cannons, the foam scrubbed off by the rollers, the
water blown off by the dryers. Those layers are decoration — but their opacity
moves **only while a matching stage is genuinely live** (or in the outro of a
turn that really ended). Idle time changes nothing.

After the turn ends, Jeremy towels the body (a real towel, orbiting the car,
with sparkles where it wipes) and vacuums the interior — the windows glow as
the inside comes clean — and Levi sends it off with a light sweep down the
bodywork. Those two run on the page's ONLY timers, strictly after a real
`turn.ended`.

Physical order is the order a real tunnel runs in, so left-to-right reads as
*further along* — and now it genuinely is: the position is a high-water mark.

Each step carries its own counter (`3× · 1.4s`) built from the harness's own
`duration_ms`. Those are the only numbers on the tunnel and every one is
measured. The counters reset when a new car pulls in, because they describe
*that car's* journey.

The office is agent-centric — a desk per agent. A car wash is task-centric — a
car enters dirty and leaves clean. That difference is why this is a separate
project and not a stylesheet.

## The invariant

> A car with a live tool call is owned by real events. No ambient or
> choreographic force may move it; only a real terminal event releases it.

`liveN` is a counter, never a boolean, so overlapping calls start the jets once
and stop them once. `syncTruth()` is the jets' only writer.

**A stage lights per in-flight call, not per car position.** Claude routinely
runs several tools at once, and each of those is genuinely a different stage
being worked on the same car — so several stages light together and a helper
appears at each one. That is where the crew comes from: every washer on stage
is standing on an unmatched `tool.started`, and there are never any idle
bystanders. The car itself sits at the furthest stage evidenced this turn,
which is a separate fact from who is working.

Consequences, all deliberate:

- **The car advances only on evidence.** A station is entered because a tool of
  that family really ran, never because time passed.
- **There is no percentage and no progress bar.** The hook stream cannot know
  how much of a turn remains, so the page never claims to. Grime thins as real
  steps complete but *plateaus*; shine is capped until the end. Only
  `turn.ended` produces a fully clean car, and the gap between "plateau" and
  "clean" is the visible difference between *work happened* and *this is done*.
- **A tool we cannot place does not move the car.** Spawning agents and asking
  the customer light an add-on instead. Guessing a stage would be inventing one.
- **No fake traffic.** A quiet session is an empty forecourt, and that is
  honest. The wash never invents activity and never invents a fault.
- **Truth does not depend on animation.** Draining the feed, the jets and the
  HUD run on their own timer, because `requestAnimationFrame` is throttled to a
  dead stop in a hidden tab — and a frozen page still displaying `● live` is
  the one thing this must never do. Only motion runs on the frame.

## What the browser can see

**It never receives `tool_input`, `tool_response`, or an agent's final message.**
Not truncated — not at all. Redaction happens at ingest, *before* the ring
buffer, so raw payloads can never be replayed to a later reconnect or appear in
`/state`. Only a derived label survives:

| tool | reaches the browser | never does |
|---|---|---|
| `Read` `Edit` `Write` | basename, or `(private file)` under `.ssh`/`.env`/`.aws`/key/secret/token patterns | full path, contents, diffs |
| `Bash` | first word, plus the subcommand for a small allowlist (`git status`) | flags, paths, pipes, redirects |
| `Grep` `Glob` | `pattern (21 chars)` | **the pattern** |
| `WebFetch` | hostname | path, query, tokens |
| `mcp__x__y` | the `x` segment | tool name, all args |
| everything else | `""` | everything |

Prompts become `{chars: N}`. Tool results become `ok` + `ms`. Targets are capped
at 60 printable ASCII characters.

Verified by assertion, not by intention:

```bash
./scripts/assert_redaction.py
```

It injects `git status --porcelain --untracked=all /etc/passwd`, an `id_rsa`
read, an `AWS_SECRET_ACCESS_KEY` grep, a URL carrying `?token=SUPERSECRET`, a
private key in `tool_response`, a prompt containing `hunter2` and an agent's
final message, then reads back **every channel the browser can reach** and fails
if any of it survives. Current result: 10 secrets injected, 0 reachable, while
`git status`, `(private file)`, `pattern (21 chars)` and the bare hostname are
correctly kept.

It also fails **inconclusive** (exit 2) if those four derived values do not turn
up — because "nothing leaked" is trivially true when nothing was injected. That
is not hypothetical: ingest de-duplicates on `(session, tool_use_id)` to stop a
replayed call stranding a jet, so with fixed ids the assertion silently stopped
testing anything on its second run and still printed PASS. Each run now uses its
own session and ids.

Transport: loopback bind only, `Host` header validated (closes DNS rebinding),
zero CORS headers, a fresh 128-bit token as a path segment on every route, and
nothing written to disk. The emitter passes `--noproxy '*'` — without it a
configured `http_proxy` would receive every payload — and refuses any marker URL
that is not `http://127.0.0.1:`.

The marker directory is `~/.claude/agent-carwash`, overridable **only** with
`AGENT_CARWASH_DATA`. It deliberately does *not* honour the shared
`CLAUDE_PLUGIN_DATA`, because doing so would let this emitter and
`agent-office`'s collide on one marker and post into each other's port.

## Files

| path | role |
|---|---|
| `ui/index.html` | the whole viewer — scene, sim, HUD, live feed. No build step, no CDN, no external request |
| `server/carwash_server.py` | ingest, redaction, ring buffer, SSE, label enrichment, watchdog |
| `scripts/carwash-emit.sh` | the hook emitter and its marker gate |
| `scripts/install-global-hooks.sh` | merge the hooks into `~/.claude/settings.json` (backs up, never replaces) |
| `scripts/assert_redaction.py` | the privacy proof |
| `skills/carwash/SKILL.md` | `open the car wash` / `close the car wash` |
| `desktop/` | Tauri v2 shell — native window, manages the server as a child process |
| `.claude-plugin/plugin.json` | plugin manifest |

Hooks are registered **project-scoped** in `../.claude/settings.json`, appended
alongside `agent-office`'s without disturbing them. Global
`~/.claude/settings.json` is untouched unless you run the installer.

## URL parameters

| param | effect |
|---|---|
| `?seed=42` | fixes the RNG stream (vehicle shapes and colours); the seed always shows in the footer |
| `?debug=1` | adds live fps, event count and drop count to the footer |
| `?reduced=1` | forces the reduced-motion branch — no particles, no wheel spin |

Opening `ui/index.html` directly, without the server, gives **demo mode**: the
same wash driven by a canned pipeline, useful for design work. It says so in the
header and in the ticket, so it can never be mistaken for a real session.

## Test hooks

`window.__CW` exposes the state the invariant is defined over:

```js
__CW.state()   // { phase, lane:{station,washed,touch,grime,state}, queue, finished, actors, jets:[…] }
__CW.info()    // { fps, nodes, seed, events, dropped }
__CW.step(60)  // advance deterministically
```

`jets` is the truth channel as a flat array — 4 stations then 6 bays — so a test
can assert the lamp state directly rather than reading pixels.

## Three bugs this build found, all worth knowing

- **Injecting at the first `</body>` is wrong.** The server appends its token
  script before the closing body tag. If that string appears earlier — in a
  comment, a template literal — the injection lands mid-document, and because
  the HTML parser ends a `<script>` element at the first closing script tag it
  sees *regardless of JavaScript syntax*, the rest of the viewer is silently
  discarded. The page loads, renders nothing, and reports no error. Fixed here
  by injecting at the **last** occurrence. `agent-office` has the same
  `replace(..., 1)` and is latently exposed to it.
- **`requestAnimationFrame` stops dead in a hidden tab.** A viewer that drains
  its event queue only from the frame loop sits frozen with a full queue while
  the header still says `● live`. Measured here: 13 events buffered, 0 applied.
  Fixed by separating state from animation — see the invariant above.
- **An `<svg>` grid item sizes the grid, not the other way round.** With
  `grid-template-columns: 1fr`, the column's automatic minimum is its content —
  and an SVG contributes an aspect-derived intrinsic width. Measured after the
  tunnel grew to nine steps: a 456 px viewport with a **578 px** column, so the
  last stations and the exit were clipped off screen with no scrollbar to hint
  at it. Fixed by taking the scene out of flow (`position:absolute; inset:0`)
  and using `minmax(0,1fr)`, so the container sizes the scene and never the
  reverse.
