# OPTSPOT AI

*Work hard, play hard, no drama.*

A car wash for your Claude Code sessions. Every car is a real tool call,
every washer is a real agent, and the jets run **if and only if** a call is
genuinely in flight. Nothing on screen is invented: the page would rather sit
empty than animate a lie.

```
Claude Code ──hooks (async, never blocking)──► carwash-emit.sh ──► carwash_server.py
   SubagentStart/Stop · Pre/PostToolUse          ~1 ms when the      redact at ingest,
   PostToolUseFailure · Stop · SessionStart       wash is closed     ring buffer + SSE
   UserPromptSubmit                                                        │
                                                                           ▼
                                                          ui/index.html — the wash
```

## Install

You need Claude Code running locally (macOS, Linux, or Windows via WSL) and
`python3` — on those systems, both are usually already there. Then:

```bash
claude plugin marketplace add rehanmunir/optspot-ai
```

```bash
claude plugin install agent-carwash@optspot
```

That is the whole install. The plugin carries its own hooks — no
`settings.json` surgery — and they only fire in sessions started *after* the
install, so open a fresh session once you're done. While the wash is closed
the hooks cost about a millisecond each and do nothing at all.

Cloud sessions can't feed it: their hooks fire on the cloud machine, and
honestly showing nothing is the whole point.

Uninstall any time with `claude plugin disable agent-carwash`, or remove the
marketplace.

## Use it

1. In any Claude Code session, say **"open the car wash"** (or *"open
   optspot"*). Claude starts the loopback server and opens the page.
2. Give Claude work — in that session or any other on the machine. Every
   tool call pulls in as its own car: reads get soaked, edits get foamed,
   commands get the rollers, and a car leaves clean only when its call
   really completes. Failed calls leave dirty. Subagents wash their own
   delegated tasks in the detail bays, and your turn is the ticket Josh
   opens and Levi closes.
3. Or order at **The Counter** on the page itself: type a job in the box and
   Claude runs it as a real local headless session — the cars you watch are
   that job being done, and the reply lands in the panel below. (The counter
   uses the standalone `claude` CLI, whose login is separate from the
   desktop app's — if it answers "not logged in", run `claude` in a terminal
   and complete `/login` once.)
4. Say **"close the car wash"** when you're done. The server removes its
   marker and the hooks go back to costing nothing.

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
| a **car** | one tool call — it enters when the call starts, leaves clean only when it completes |
| the **ticket** | one turn — Josh opens it at your prompt, Levi closes it at turn end |
| a **washer** | one agent |
| a **detail bay** | one subagent, washing its own delegated task |
| **jets running** | a real tool call is in flight — the whole truth channel |
| an **add-on service** | real work that is not a wash stage (spawning agents, checklists, asking you) |

Parallel calls are several cars in the tunnel at once, because that is what
they really are. A failed call skips the towel and leaves as dirty as it
came. Cars queue on the belt in arrival order, like a real backed-up tunnel.
The car IS the in-flight call, so cars, lamps and machinery can never
disagree.

### Four phases, four staff

| phase | staff | on duty when |
|---|---|---|
| **CHECK-IN** | Josh | the ticket is open and no call is in flight — the welcome, and the thinking |
| **THE TUNNEL** | Nick | cars in the wash — one per in-flight call |
| **TOWEL & INTERIOR** | Jeremy | a car that really completed is being dried |
| **GOODBYE** | Levi | a finished car is seen off — clean, or dirty if its call failed |

Thinking is evidenced, not guessed: it is the exact complement of "a call is
in flight" inside an open ticket. The thought bubble hangs over Josh's podium
and says *no call in flight* — never what Claude is thinking about, because
the stream doesn't carry that.

Everything is event-driven except two short per-car dwells (Jeremy's towel,
Levi's goodbye), each of which runs strictly after that car's own real
completion — an outro for something that genuinely happened, never a claim
about work still in progress. The closed ticket is measured facts only:
washed, failed, elapsed — the viewer never receives Claude's reply.

### The four stages

| # | stage | machinery | evidence |
|---|---|---|---|
| 1 | WATER POUR | overhead pipe, pouring nozzles | `Read` `Grep` `Glob` `WebFetch` … — soaking the task |
| 2 | SOAP & FOAM | three coloured foam cannons | `Write` `Edit` — laying the new material on |
| 3 | ROLLERS | striped side brushes + top roller | `Bash` `mcp__*` — scrubbing it all over |
| 4 | AIR DRY | blower bank | the exit ride — fires only for a car whose call really completed |

The chain never stops: a live car creeps forward through every arch — wet
sheen under the water, clinging foam under the cannons, foam scrubbed off by
the rollers — easing to a stop at the **hold line** before the dryers. Its
position shows how long its call has been running, never how close it is to
done; only the real completion event carries a car across the line. Each arch
fires exactly while a live car is under it — a car straddling two arches
lights both, the way a real tunnel's tail is still in the water curtain as
the nose meets the foam.

On completion the car rides out through the blowers, gets Jeremy's towel, and
Levi waves it off gleaming. On failure it skips the towel and leaves dirty,
plate stamped ✗. AIR DRY fires only for completed cars riding out — there is
no way to reach it by waiting.

Each stage shows `passes × total-ms` from the harness's own `duration_ms` —
the only numbers on the tunnel, every one measured, reset per ticket.

## Ask at the counter

The wash has a counter: type a job into the box on the page and Claude does
it while you watch. The server runs your prompt as a real, local, headless
Claude Code session (`claude -p`) — that session's hooks light the wash live,
so the cars you see ARE your job being done — and the reply lands back in the
panel when it finishes.

This does not weaken the redaction, and the distinction matters: the hook
*stream* (any session's activity) stays as redacted as ever; the counter only
returns the output of the order **you personally placed through it**, over
the same tokenised loopback socket, gated exactly like `/close`. One order at
a time, five-minute cap, never buffered or logged. The spawned session runs
with your own Claude Code auth and default print-mode permissions — mostly
reads and searches, which is precisely what lights the tunnel. One setup
note: the standalone `claude` CLI keeps its own login, separate from the
desktop app's — if the counter answers "not logged in", run `claude` in a
terminal and complete `/login` once.

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

The OptSpot wordmark on the marquee belongs to [optspot.com](https://optspot.com)
and is embedded here with the owner's blessing; the page still makes zero
external requests — the mark ships inline.

`window.__CW` exposes the state the invariant is defined over, so tests can
assert lamp state directly instead of reading pixels:

```js
__CW.state()   // { phase, turn:{open,spawned,washed,failed,queue}, cars:[{tool,stage,state,grime}], finished, actors, jets:[…] }
__CW.info()    // { fps, nodes, seed, events, dropped }
__CW.step(60)  // advance deterministically
```
