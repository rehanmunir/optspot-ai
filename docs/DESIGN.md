# Design notes

How the wash stays honest, for anyone reading the code.

```
Claude Code ──hooks (async, never blocking)──► carwash-emit.sh ──► carwash_server.py
   SubagentStart/Stop · Pre/PostToolUse          ~1 ms when the      redact at ingest,
   PostToolUseFailure · Stop · SessionStart       wash is closed     ring buffer + SSE
   UserPromptSubmit                                                        │
                                                                           ▼
                                                          ui/index.html — the wash
```

## The invariant

> A car with a live tool call is owned by real events. No ambient or
> choreographic force may move it; only a real terminal event releases it.

`liveN` is a counter, never a boolean, so overlapping calls light a lamp once
and put it out once. `syncTruth()` is the only writer of lamp state.

A car **is** an in-flight call: it spawns on `tool.started` and is released by
`tool.finished`. Because the cars are the truth channel, cars, lamps and
machinery cannot disagree with each other.

Precisely: a lane car is a *main-session* call whose tool maps to a stage.
Everything else real still shows, elsewhere — a subagent's calls drive its
bay, and unmapped tools (`TodoWrite`, `Task`, `AskUserQuestion`, …) light an
add-on chip. The thought bubble accounts for all of them: it will not say
"no call in flight" while any actor has one.

Consequences, all deliberate:

- **No percentage, no progress bar.** The hook stream cannot know how much of
  a turn remains, so the page never claims to. A car's position shows how long
  its call has *run*, never how close it is to done — it eases to a stop at a
  hold line before the dryers, and only the real completion event carries it
  across.
- **A failed call leaves dirty.** No towel, no gleam, plate stamped ✗ — and
  it never rides AIR DRY, which is reserved for calls that actually
  succeeded. (That last stage is therefore the one lamp that lights just
  *after* a call ends rather than during it.)
- **A turn ending closes its cars.** `turn.ended` is terminal evidence, so any
  call still open at that instant is finished as far as the stream can ever
  know, and its car is released clean rather than left stranded.
- **Thinking is evidenced, not guessed.** It is the exact complement of "a call
  is in flight" inside an open ticket. The thought bubble says *no call in
  flight* — never what Claude is thinking about, because the stream doesn't
  carry that.
- **No fake traffic, no fake people.** A quiet session is an empty forecourt.
  The customers appear only while your ticket is genuinely open.
- **Truth doesn't depend on animation.** Draining the feed, the lamps and the
  HUD run on their own timer, because `requestAnimationFrame` stops dead in a
  hidden tab — and a frozen page still displaying `● live` is the one thing
  this must never do. Only motion runs on the frame.
- **Timers never move a car during work.** Three exist, all after the fact:
  the towel dwell, the goodbye dwell, and the same dwell for a rejected car
  leaving. (Two more touch no car at all — the state pump, and the bay
  teardown linger.)

## Motion

State snaps on the frame evidence arrives; only the pixels ease. One fade
engine (fast attack, slower release) drives every halo, glow and character —
but the lamp fill itself snaps, because it is the truth indicator.

Cars have physics: velocity proportional to distance (decelerate-in),
accelerate-out exits, suspension settle after a stop, a harder shake under the
rollers they are genuinely beneath, an antenna that lags and whips. A green
ring pulses on the frame a call really completes. Vehicle shape and paint —
including the exotics — are pure variety and never carry meaning.

Under `prefers-reduced-motion` (or `?reduced=1`) nothing translates: cars
park at their own stage instead of riding the belt, and particles, rings and
secondary motion are off. A hidden tab snaps everything, so no easing debt
accumulates while you are not looking.

## What the browser can see

| tool | reaches the browser | never does |
|---|---|---|
| `Read` `Edit` `Write` | basename, or `(private file)` for `.ssh`/`.env`/key/secret/token patterns | full path, contents, diffs |
| `Bash` | first word, plus the subcommand for a small allowlist (`git status`) | flags, paths, pipes |
| `Grep` `Glob` | `pattern (21 chars)` | **the pattern** |
| `WebFetch` | hostname | path, query, tokens |
| `mcp__x__y` | the server segment (`x`) as the label | the arguments |
| `Agent` `Task` | the subagent type | the prompt it was given |
| `WebSearch` | the words `web search` | the query |
| everything else | `""` | everything |

The **tool name itself** is always sent — that is what the activity feed
lists. What the table governs is the *label* beside it, derived from
`tool_input`.

Two other channels reach the page and are worth naming: a subagent's own
one-line description (up to 60 chars, from its meta file, shown on its bay),
and the working directory's basename at session start. Prompts become
`{chars: N}`. Results become `ok` + `ms`. Redaction happens at ingest, before
the ring buffer, so raw payloads can never be replayed to a later reconnect
or appear in `/state`.

A `Bash` command's leading environment assignments are stepped over before
the first word is taken — `SECRET=xyz aws s3 ls` reports `aws`, never the
assignment — and a secret-shaped argv[0] reports nothing at all.

`scripts/assert_redaction.py` proves it: it fires an `id_rsa` read, an
`AWS_SECRET_ACCESS_KEY` grep, a `?token=SUPERSECRET` URL, a private key in a
tool response and a password in a prompt through the real ingest endpoint, and
fails if any of it reaches anything the browser can read. It also fails
*inconclusive* if the expected derived values never arrive — because "nothing
leaked" is trivially true when nothing was sent.

Transport: loopback bind only, `Host` header validated, zero CORS headers, a
fresh 128-bit token in every URL path. No event data is ever written to disk
and there is no request log — the only files the server touches are two
markers in `~/.claude/agent-carwash/` (`carwash.live`, `carwash.json`) holding
its pid, port, url and token so the hooks can find it, removed on exit. The
emitter refuses any marker URL that is not `http://127.0.0.1:` and passes
`--noproxy '*'` so a configured proxy never sees a payload.

### The counter

`/ask` runs your prompt as a real local `claude -p` session, so its reply —
Claude's actual words — does come back to the page. That is the counter's
whole purpose, and it is the one exception to everything above: the hook
*stream* stays redacted, and the counter returns only the output of the order
you personally placed through it, over the same tokenised socket, one order
at a time, five-minute cap. The wash never logs it; the spawned session keeps
its own transcript under `~/.claude/projects`, exactly like any other Claude
Code session.

## Files

| path | role |
|---|---|
| `ui/index.html` | the whole viewer — scene, sim, HUD, live feed; no build step, no CDN, zero external requests |
| `server/carwash_server.py` | ingest, redaction, ring buffer, SSE, watchdog — stdlib only, Python ≥3.9 |
| `scripts/carwash-emit.sh` | the hook emitter and its marker gate |
| `scripts/assert_redaction.py` | the privacy proof |
| `hooks/hooks.json` | plugin-managed hook registration |
| `skills/carwash/SKILL.md` | *open the car wash* / *close the car wash* |

## Test hooks

`window.__CW` exposes the state the invariant is defined over, so tests assert
lamp state directly instead of reading pixels:

```js
__CW.state()   // { phase, turn:{open,spawned,washed,failed,queue}, cars:[{tool,stage,state,grime}], finished, actors, jets:[…] }
__CW.info()    // { fps, nodes, seed, events, dropped }
__CW.step(60)  // advance deterministically
```

## Two bugs worth knowing

- **Injecting at the first `</body>` is wrong.** The server appends its token
  script before the closing body tag. If that string appears earlier — in a
  comment, a template literal — the injection lands mid-document, and because
  the HTML parser ends a `<script>` at the first closing script tag it sees
  *regardless of JavaScript syntax*, the rest of the viewer is silently
  discarded. The page loads, renders nothing, and logs no error. Fixed by
  injecting at the **last** occurrence.
- **`requestAnimationFrame` stops dead in a hidden tab.** A viewer that drains
  its event queue only from the frame loop sits frozen with a full queue while
  the header still says `● live`. Measured before the fix: 13 events buffered,
  0 applied. Fixed by separating state from animation.
