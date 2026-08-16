# OPTSPOT AI

A car wash for your Claude Code sessions. Every car is a real task, every
washer is a real agent, and the jets run **if and only if** a real tool call
is in flight. Nothing on screen is invented: the page would rather sit empty
than animate a lie.

```
Claude Code ──hooks (async, never blocking)──► carwash-emit.sh ──► carwash_server.py
   SubagentStart/Stop · Pre/PostToolUse          ~1 ms when the      redact at ingest,
   PostToolUseFailure · Stop · SessionStart       wash is closed     ring buffer + SSE
   UserPromptSubmit                                                        │
                                                                           ▼
                                                          ui/index.html — the wash
```

## Install

The repo is its own plugin marketplace:

```bash
claude plugin marketplace add rehanmunir/optspot-ai
claude plugin install agent-carwash@optspot
```

That wires all eight hooks (plugin-managed — no `settings.json` surgery) and
ships the skill, so you can just tell Claude *"open the car wash"* or *"open
optspot"* in any session. Hooks cost ~1 ms each while the wash is closed and
do nothing.

Runs anywhere Claude Code runs locally with a POSIX shell: macOS, Linux, and
Windows via WSL. Cloud sessions can't feed it — their hooks fire on the cloud
machine, and honestly reporting nothing is the whole point.

Uninstall: `claude plugin disable agent-carwash`, or remove the marketplace.

## Run it by hand

```bash
python3 server/carwash_server.py
```

Prints a tokenised URL and opens a browser (`--no-browser` to skip). Close it
by POSTing to `<url>close`, or kill the pid recorded in
`~/.claude/agent-carwash/carwash.json` — the server removes its marker on
exit, which returns the hooks to their do-nothing fast path.

Opening `ui/index.html` directly, without the server, gives demo mode: the
same wash driven by canned traffic. It says so on screen, loudly, so it can
never be mistaken for a real session.

## How to read it

| on screen | what it actually is |
|---|---|
| a **car** | one turn — your prompt in, Claude's turn ended |
| a **washer** | one agent |
| the **tunnel** | main Claude's work on your turn |
| a **detail bay** | one subagent, washing its own delegated task |
| **jets running** | a real tool call is in flight — the whole truth channel |
| an **add-on service** | real work that is not a wash stage (spawning agents, checklists, asking you) |

### Four phases, four staff

| phase | staff | entered when |
|---|---|---|
| **CHECK-IN** | Josh | a prompt is open and no tool has run yet — the welcome |
| **THE TUNNEL** | Nick | a tool call is in flight — the four stages |
| **TOWEL & INTERIOR** | Jeremy | `turn.ended` fired — towel dry, vacuum the inside |
| **GOODBYE** | Levi | the ticket is read back, then the clean car leaves |

Thinking is evidenced, not guessed: it is the exact complement of "a call is
in flight" inside an open turn. The thought bubble says *no call in flight* —
never what Claude is thinking about, because the stream doesn't carry that.

Josh and Nick are driven purely by events. Jeremy and Levi run on a short
timer, the only timed moves on the page — an outro for something that
genuinely happened, never a claim about work still in progress. Levi's
goodbye is deliberately thin: the viewer never receives Claude's reply, so
the ticket is measured facts only — calls completed, touch-ups, elapsed time.

### The four stages

| # | stage | machinery | evidence |
|---|---|---|---|
| 1 | WATER POUR | overhead pipe, pouring nozzles | `Read` `Grep` `Glob` `WebFetch` … — soaking the task |
| 2 | SOAP & FOAM | three coloured foam cannons | `Write` `Edit` — laying the new material on |
| 3 | ROLLERS | striped side brushes + top roller | `Bash` `mcp__*` — scrubbing it all over |
| 4 | AIR DRY | blower bank | the exit ride — fired by `turn.ended`, nothing else |

**The conveyor never runs backwards.** A real tunnel is a chain: forward or
hold, never reverse. The car's position is the furthest stage evidenced this
turn — advanced only by real calls, never by time. When an earlier-family
call runs after the car has moved on, that stage's lamp lights and its washer
takes the work *to the car*: a touch-up crew, counted on the ticket. The
machinery is sensor-driven like the real thing — an arch only runs with the
car under it.

The car visibly changes as stages really run: wet sheen under the water,
clinging foam under the cannons, foam scrubbed off by the rollers, water
blown off by the dryers. Those layers are decoration, but their opacity moves
only while a matching stage is genuinely live. Idle time changes nothing.

A stage lights **per in-flight call**, not per car position — Claude runs
tools in parallel, and each call is genuinely a different stage being worked
on the same car. Every washer on stage is standing on an unmatched
`tool.started`; there are no idle bystanders. Grime thins as real calls
complete but plateaus; only the turn ending makes a car fully clean, and the
gap between those two looks is the difference between *work happened* and
*this is done*.

Each stage shows `passes × total-ms` from the harness's own `duration_ms` —
the only numbers on the tunnel, every one measured, reset per car.

## What the browser can see

**It never receives `tool_input`, `tool_response`, prompt text, or an agent's
final message.** Not truncated — not at all. Redaction happens at ingest,
before the ring buffer, so raw payloads cannot be replayed to a later
reconnect or appear in `/state`. Only a derived label survives:

| tool | reaches the browser | never does |
|---|---|---|
| `Read` `Edit` `Write` | basename, or `(private file)` for `.ssh`/`.env`/key/secret/token patterns | full path, contents, diffs |
| `Bash` | first word, plus the subcommand for a small allowlist (`git status`) | flags, paths, pipes |
| `Grep` `Glob` | `pattern (21 chars)` | **the pattern** |
| `WebFetch` | hostname | path, query, tokens |
| `mcp__x__y` | the `x` segment | tool name, all args |
| everything else | `""` | everything |

Prompts become `{chars: N}`. Results become `ok` + `ms`. This is enforced by
test, not intention: `scripts/assert_redaction.py` fires hostile payloads —
an `id_rsa` read, an `AWS_SECRET_ACCESS_KEY` grep, a `?token=SUPERSECRET`
URL, a private key in a tool response, a password in a prompt — through the
real ingest endpoint and fails if any of it reaches anything the browser can
read. It also fails *inconclusive* if the expected derived values never
arrive, because "nothing leaked" is trivially true when nothing was sent. CI
runs it on every push.

Transport: loopback bind only, `Host` header validated, zero CORS headers, a
fresh 128-bit token in every URL path, nothing written to disk. The emitter
refuses any marker URL that is not `http://127.0.0.1:` and passes
`--noproxy '*'` so a configured proxy never sees a payload.

## Files

| path | role |
|---|---|
| `ui/index.html` | the whole viewer — scene, sim, HUD, live feed; no build step, no CDN, zero external requests |
| `server/carwash_server.py` | ingest, redaction, ring buffer, SSE, watchdog — stdlib only, Python ≥3.9 |
| `scripts/carwash-emit.sh` | the hook emitter and its marker gate |
| `scripts/assert_redaction.py` | the privacy proof |
| `hooks/hooks.json` | plugin-managed hook registration |
| `skills/carwash/SKILL.md` | *open the car wash* / *close the car wash* |

## URL parameters

| param | effect |
|---|---|
| `?seed=42` | fixes the RNG stream (vehicle shapes and colours) |
| `?debug=1` | live fps, event count and drop count in the footer |
| `?reduced=1` | forces reduced motion — no particles, no wheel spin |

`window.__CW` exposes the state the invariant is defined over, so tests can
assert lamp state directly instead of reading pixels:

```js
__CW.state()   // { phase, lane:{station,washed,touch,grime,state}, queue, finished, actors, jets:[…] }
__CW.info()    // { fps, nodes, seed, events, dropped }
__CW.step(60)  // advance deterministically
```
