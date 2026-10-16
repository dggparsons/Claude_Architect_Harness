# Working practice
The plan, review loop and severity scale the harness's skills use. They ship with the harness so they work on any machine. If your own `~/.claude/CLAUDE.md` defines its own plan template, loop or severity scale, use yours; this file is the default when it does not.

## 1. Every project runs from a plan
- **Find the plan first.** Look for `PLAN.md`, a `_project/` folder or a README status list. Use it and keep it current. Never start a second plan.
- **No plan? Write one** from the template below before building anything substantial, and show the owner the phase list before build work starts.
- **Phases run in order**, each with a goal, its tasks and an exit gate. A typical sequence: 0 Discover, 1 Research (every claim the work needs has a checked source), 2 Design, 3 Build content (every task clean), 4 Produce (outputs built from source by script, and they open, render and play), 5 Final QA and handover (end-user walkthrough clean).
- **Content before production.** Rendering, recording, packaging or deploying waits until the source has passed its loop.
- **Small tasks**, each finishable and provable in one sitting.
- **Decisions** only the owner can make go in the plan with a recommended default, so work continues around them.
- **Status** is kept current: the plan answers "where are we" without anyone reading the chat.

### Plan template
```markdown
# <Project> – Plan
**Goal:** one paragraph: what we are making, for whom, and what "finished" means.
**Example of good:** the reference to match, if any (read-only).
**Constraints:** deadlines, formats, tools, brand, things not to touch.

## Phases
| Phase | Goal | Exit gate | Status |
|---|---|---|---|

## Tasks
| ID | Phase | Task | Done when (testable) | Depends on | Status |
|---|---|---|---|---|---|
Status: todo · building · in loop (round N) · clean · blocked (why)

## Decisions for the owner
| # | Decision | Recommended default | Status |
|---|---|---|---|

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|

## Log
- YYYY-MM-DD: what changed and why
```

## 2. The review loop: plan, build, QA, test, fix, repeat until clean
1. **Plan the task:** goal, testable done-when checks, files it touches, how it will be tested.
2. **Build.** No placeholders (TODO, TBC, dummy text) unless logged as decisions.
3. **QA with an independent reviewer:** a fresh subagent that did not build the work (the harness's `reviewer-*` agents), given the done-when checks and told to find problems, quote the exact text and propose the exact fix. For important work, several reviewers in parallel, one lens each. Whoever built the work never marks it clean.
4. **Test it as it will be used:** run the code and tests; open, render or play the output; walk through it as the real user. Record real results, including failures.
5. **Fix** every High and Medium at its root cause, and quick Lows. Fix the source, not the generated copy, then search for the same problem everywhere else.
6. **Repeat QA and test** on what changed. Clean = a full round with nothing High or Medium and every done-when check passing.
7. **Close:** log what was found and fixed, and anything deferred with the reason; update the plan.
If the same finding returns after two fix rounds, or a task passes four rounds without coming clean, stop looping: write down what keeps going wrong, change the approach, and tell the owner.

## 3. Severity
- **High:** wrong, broken, unsafe or misleading; would embarrass the owner in front of a customer; fails a done-when check.
- **Medium:** confusing, inconsistent between files, or makes the next person's job harder.
- **Low:** cosmetic.

## 4. Review records
Keep findings in the project's review folder (for example `_project/review/`), one file per round, as a table `# | Severity | File:line | Problem | Evidence | Fix | Status`, plus a short response log of what was applied, what was not, and why.

## 5. Standards for all work
- **Verify, don't assume.** Every factual claim traces to a source you have read; date anything that changes; if you cannot verify it, say so or leave it out.
- **Never invent an identifier.** Check every path, ID, version, CVE and file name exists before writing it; if you cannot, mark it unverified.
- **Fail loudly.** A check that cannot run reports "not run", never "pass".
- **Safe bulk edits.** Script bulk changes so that every replacement is checked to match the expected number of times, and nothing is written if one fails.
- **Secrets** stay in environment variables or untracked local files, never in committed files, logs or command lines.
- **Ask first** before anything destructive or outward-facing: deleting, overwriting, publishing, sending, pushing.
