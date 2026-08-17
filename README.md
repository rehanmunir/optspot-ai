# OPTSPOT AI

*Work hard, play hard, no drama.*

Watch Claude Code work, as a car wash. Every tool call drives in as its own
car, gets soaked and foamed and scrubbed while the call runs, and leaves
clean the moment it finishes. Your agents are the crew.

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
machine. Cars start rolling in — one per tool call.

**3. Or order from the page.** Type a job into **The Counter** box and hit
*ask*. Claude runs it right there; you watch the cars while it works, and the
answer appears underneath.

**4. Close it** when you're done:

> close the car wash

The hooks go back to costing nothing (~1 ms each, doing no work at all).

Uninstall any time with `claude plugin disable agent-carwash`.

## What you're watching

| on screen | what it is |
|---|---|
| a **car** | one tool call |
| the **ticket** | one turn — your prompt to Claude's reply |
| a **washer** | one agent |
| a **detail bay** | one subagent, working its own task |
| **jets running** | a real tool call is in flight right now |

Cars move through four stages, and each one means something:

| stage | what Claude is doing |
|---|---|
| **WATER POUR** | reading and searching |
| **SOAP & FOAM** | writing and editing |
| **ROLLERS** | running commands, calling services |
| **AIR DRY** | the ride out — the call finished |

Several calls at once means several cars in the tunnel. A car only leaves
clean when its call actually completes; **a failed call leaves dirty**, plate
stamped ✗. Four staff work the shop: **Josh** checks you in, **Nick** runs
the tunnel, **Jeremy** towels and vacuums, **Levi** waves you off.

There's no progress bar anywhere, on purpose — see [the design
notes](docs/DESIGN.md) for why.

## Your data stays yours

The page never receives file contents, command lines, tool output, search
patterns, your prompts, or Claude's replies. It gets tool names and short
harmless labels — a filename like `index.html`, or `(private file)` for
anything sensitive; `git status` but never the flags; `pattern (21 chars)`
but never the pattern.

Redaction happens on the way in, before anything is stored. The server is
loopback-only with a fresh token in every URL, and writes nothing to disk.
This is enforced by a test that fires real secrets at it and fails if any
survive — CI runs it on every push.

## Troubleshooting

**The wash is live but nothing moves.** Hooks only fire in sessions started
after you installed the plugin — open a new one. (An empty forecourt while
Claude is idle is just correct.)

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
  counts, `?reduced=1` turns off motion

The OptSpot wordmark belongs to [optspot.com](https://optspot.com) and ships
inline — the page makes zero external requests.
