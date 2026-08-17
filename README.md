# OPTSPOT AI

*Work hard, play hard, no drama.*

Watch Claude Code work, as a car wash. Every time Claude reads, writes or
runs something, a car drives in — soaked and foamed and scrubbed while the
call runs, leaving clean the moment it finishes. Your agents are the crew.

Nothing on screen is invented — if Claude is idle, the forecourt is empty.

## Install

You need Claude Code running locally (macOS, Linux, or Windows via WSL) and
`python3`. Both are usually already there.

```bash
claude plugin marketplace add rehanmunir/optspot-ai
```

```bash
claude plugin install agent-carwash@optspot
```

Then **start a new Claude Code session** — the hooks only fire in sessions
opened after the install.

## Use it

**1. Open the wash.** In any Claude Code session, say:

> open the car wash

Claude starts a local server and opens the page. Keep it in a side window.

**2. Give Claude work.** Anything, in that session or any other on this
machine. Cars start rolling in. (Work that isn't a read, write or command —
spawning a subagent, ticking a to-do, asking you a question — lights an
add-on chip on the ticket instead, and subagents wash their tasks in the
bays.)

One wash shows one session. If you have several Claude Code windows open, a
picker appears in the header — the wash follows whichever session is newest
until you choose one, and then it stays where you put it.

**3. Or order from the page.** Type a job into **The Counter** and press
Enter (Shift+Enter for a new line). Claude runs it right there — you watch the
cars while it works, and the answer lands in the panel underneath, kept with
what you asked so you can read them together. Pick a **model** and an
**effort level** beside the ask button if you want; both are remembered.

**4. Close it** when you're done:

> close the car wash

The hooks go back to costing nothing (~1 ms each, doing no work at all).

To switch it off for a while: `claude plugin disable agent-carwash@optspot`.
To remove it for good: `claude plugin uninstall agent-carwash@optspot`.

## What you're watching

| on screen | what it is |
|---|---|
| a **car** | one of Claude's reads, writes or commands |
| the **ticket** | one turn — your prompt to Claude's reply |
| a **washer** | one agent |
| a **detail bay** | one subagent, working its own task |
| **jets running** | a real tool call is in flight right now |

Every car rides the whole tunnel, the way a real one does — and the tally
under each arch counts the kind of work that came through it:

| stage | counts |
|---|---|
| **WATER POUR** | reading and searching |
| **SOAP & FOAM** | writing and editing |
| **ROLLERS** | running commands, calling services |
| **AIR DRY** | the ride out, once a call has succeeded |

A car's position shows how long its call has been running — it creeps up to a
line before the dryers and waits there, because nothing can know how much
longer a call needs. Several calls at once means several cars in the tunnel.
**A failed call leaves dirty**, plate stamped ✗, skipping the dryers and the
towel.

The shop is run by **Josh** at check-in, **Nick** through the tunnel,
**Jeremy** on towel and interior, and **Levi** waving you off.

There's no progress bar anywhere, on purpose — see [the design
notes](docs/DESIGN.md) for why.

## Your data stays yours

Watching costs you nothing in privacy. From everything Claude does, the page
receives tool names and short harmless labels — a filename like `index.html`,
or `(private file)` when the path looks sensitive; `git status` but never the
flags; `pattern (21 chars)` but never the pattern. It never receives file
contents, command lines, tool output, search patterns, or your prompts and
replies.

The one thing that does come back in full is the answer to an order **you**
typed into The Counter — that is the point of the counter, and it goes only
to the page that placed it.

Redaction happens on the way in, before anything is stored, and **no event
ever touches disk** — the server keeps them in memory and forgets them when
it stops. It binds to loopback only, with a fresh token in every URL. (It
does write two small marker files in `~/.claude/agent-carwash/`, holding its
pid, port and that token, so the hooks can find it; they're deleted on exit.)

This is enforced by a test that fires real secrets at it and fails if any
survive — CI runs it on every push.

## Troubleshooting

**The wash is live but nothing moves.** Hooks only fire in sessions started
after you installed the plugin — open a new one. (An empty forecourt while
Claude is idle is just correct.) If a new session doesn't help, check you
have `curl`: the hook emitter uses it, and it stays silent when it's missing
rather than ever colouring a hook red.

**The counter says "not logged in".** The standalone `claude` CLI keeps its
own login, separate from the desktop app's. Run `claude` in a terminal and
complete `/login` once.

**Want to run it without the plugin?** `python3 server/carwash_server.py`
prints a URL and opens it. Opening `ui/index.html` directly gives a demo mode
with canned traffic — it says so on screen.

## More

- [Design notes](docs/DESIGN.md) — how the wash stays honest, and why there's
  no progress bar
- URL options: `?seed=42` fixes the vehicles, `?debug=1` shows fps and event
  counts, `?reduced=1` parks the cars and drops the particles (it's also
  automatic if your system asks for reduced motion)

The OptSpot wordmark belongs to [optspot.com](https://optspot.com) and ships
inline — the page makes zero external requests.
