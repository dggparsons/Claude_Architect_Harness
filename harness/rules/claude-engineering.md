# Claude engineering standards (always on)
Distilled from the Claude Certified Architect (Foundations) curriculum and checked against Anthropic's docs on 2026-10-14. Tags like [3.4] point to modules in the `claude-engineering` skill references. These add to `~/.claude/CLAUDE.md`; where the two seem to differ, `~/.claude/CLAUDE.md` wins.

## Plan or act
- Plan first (plan mode or a written plan) for ambiguous, multi-file, architectural or migration work; act directly on small, well-understood fixes. [3.4]
- For an unfamiliar domain or an under-specified request, find out the few things that change the design before building. [3.5]
- When output is inconsistent, give or ask for concrete examples or test cases; a few worked examples (Anthropic suggests 3–5) beat more adjectives. [3.5, 4.2]

## Delegating to subagents
- A new subagent does not see this conversation (only a fork does). Brief it like a new colleague: goal, done-when checks, exact paths, findings so far, constraints, and the output format you want back. [1.3]
- Ask for structured results (paths, symbols, claims with sources, status), not prose, so they can be merged and checked. [1.3, 5.3]
- Split work so scopes do not overlap and together cover the whole request. Launch independent subagents in one message so they run in parallel, unless they share a one-at-a-time resource such as a shared local-model queue. [1.2, 1.3]
- Send verbose exploration (large searches, log trawls, many-file reads) to a subagent and keep only its summary in the main context. [3.4, 5.4]
- When a delegated result is bad, check the brief and the split before blaming the worker. [1.2]

## Context and long sessions
- On long jobs keep a state file in the project (the plan, or a notes file next to it, not the session scratchpad, so a fresh session can find it) with exact paths, symbols, decisions and open questions, and re-read it rather than relying on earlier turns. Copy facts that must not drift (IDs, figures, dates) word for word. [5.1, 5.4]
- Before compaction or a fresh session, write down what is done, what was found, the current phase and next steps. Compact at phase boundaries, not mid-task. [5.4]
- Tool results go stale when files change: re-read changed files before relying on them, and on long jobs prefer a fresh session seeded with a summary of what changed. [1.7]
- Signs of context degradation: vague "typical pattern" answers, repetition, contradicting earlier findings. When they appear, re-read the state file or restart with a summary. [5.4]

## Tools and search
- Use the most specific tool: Grep for content and Glob for paths (built in on Windows; on other platforms Claude Code searches through Bash), Edit for targeted changes. Explore incrementally; never bulk-read a codebase. [2.5]
- An empty result from a search that ran is an answer ("none found"); a search that failed is not. Never report one as the other. [2.2, 5.3]

## Errors, retries and open questions
- A failure report carries what was attempted, what failed, any partial results and what could be tried next. [2.2, 5.3]
- Check that every path, ID, version and CVE exists before you write it; if you cannot check it, mark it unverified or leave it out.
- Retry only what can succeed on retry, feeding the specific error back. Stop after two failed retries of the same fix and change approach or raise it. Busy or queue responses (such as a shared local model's 503) follow that service's own back-off rules instead (your `~/.claude/CLAUDE.md` may define them). Never retry "the data is not in the source". [4.4]
- When something only the user can decide comes up, log it as a decision with a recommended default and carry on around it. Ask straight away only when you are blocked: something matches more than one target and the wrong choice would do harm, or the action is destructive or outward-facing. Decide on these facts, not on the user's tone. When you cannot verify something, say so in your answer rather than stopping to ask. [5.2]

## Instructions, prompts and briefs you write
- State explicit criteria: what to report, what to skip, how to rate severity, with an example per level. "Be careful" or "only high-confidence findings" are not criteria. [4.1]
- When information is absent, the output says null or "not found" and flags it. Never fill a gap with a plausible value. [4.3, 4.4]
- Review in two layers: each file or unit on its own, then one cross-file pass for consistency. [1.6, 4.6]

## Sources and synthesis
- Keep each claim's source (URL or file:line, excerpt, date) attached through every step, including the final synthesis, where provenance is most often lost. Show conflicting sources side by side with dates, and state coverage gaps in the output itself. [5.3, 5.6]

## Claude Code configuration
- CLAUDE.md and rules files guide Claude; they do not enforce. A rule that must hold every time becomes a `settings.json` permission rule or a hook: propose that rather than adding another sentence. [1.4, 3.1]
- Put each instruction at the right level: team conventions in the project `CLAUDE.md` or `.claude/rules/`; personal preferences in `~/.claude/`; file-type conventions in path-scoped rules; repeatable procedures in skills. [3.1–3.3]
- Before creating or editing a `CLAUDE.md`, rules file, skill, subagent, `settings.json`, hook or `.mcp.json`, make sure `~/.claude/rules/claude-code-config.md` is in context (it is set to load when such files are touched); if it is not, read it first.
- For building anything Claude- or LLM-powered, use the `claude-engineering` skill. When substantial work starts in a project with no `CLAUDE.md`, suggest `/claude-eng-setup` once; to review an existing project against these standards, suggest `/claude-eng-audit`; when asked whether a setup works, run the `claude-eng-doctor` check.
