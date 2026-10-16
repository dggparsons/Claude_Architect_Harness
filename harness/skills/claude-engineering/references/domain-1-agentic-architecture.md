# Domain 1: Agentic Architecture & Orchestration – Engineering Standard

**Exam weight:** 27% (Exam Guide v1.0, July 2026, as reported on the exam-overview page of claudecertificationguide.com).
**Modules:** 1.1 Agentic Loops · 1.2 Multi-Agent Orchestration · 1.3 Subagent Invocation and Context Passing · 1.4 Workflow Enforcement and Handoff · 1.5 Agent SDK Hooks · 1.6 Task Decomposition Strategies · 1.7 Session State and Resumption.
**Sources:** the Domain 1 lesson pages of the third-party guide at claudecertificationguide.com (tagged [1.1] to [1.7]), its Domain 1 quick reference [QR], glossary [GL] and exercises page.
**Status:** Technical claims checked against Anthropic's docs on 2026-10-14; corrections applied inline. Evidence: `references/verification.md`.

---

## 1.1 Agentic Loops

**Rules**
- Drive the loop from `stop_reason`, never from the response text. Continue on `"tool_use"`, finish on `"end_turn"`. [1.1]
- On `"tool_use"`, run every requested tool, then append the assistant response and a user message carrying the `tool_result` blocks to the history before the next call. A loop that drops tool results leaves the model with nothing new to reason about. [1.1]
- Treat any `stop_reason` other than `end_turn` as "not finished: find out why". Handle `pause_turn`, `max_tokens`, `stop_sequence`, `refusal` and `model_context_window_exceeded` explicitly; do not assume a non-`end_turn` value means `tool_use`. On `refusal`, branch on `stop_reason` (not on `stop_details.category`, which can be `null`), log `stop_details`, and retry on a fallback model where appropriate. [1.1]
- Add an iteration cap only as a safety net against runaway loops (the exercise uses 20), log a warning when it fires, and expect it never to fire in normal use. Never make it the primary stop condition. [1.1]
- Prefer model-driven tool selection over hard-coded decision trees, except where business logic needs deterministic compliance (money, security, regulation); there, enforce in code (see 1.4). [1.1]
- When diagnosing premature termination, fix the termination check; do not raise the iteration cap. [1.1]

**Anti-patterns to catch in review**
- `response.content[0].type == "text"` (or any "has text" test) used to decide completion. Text can sit beside `tool_use` blocks in the same response. [1.1]
- String matching on "done", "task complete", "I have finished" to end the loop. [1.1]
- `while i < N` with no `stop_reason` check, or a cap raised to "fix" early exits. [1.1]
- `tool_choice` forced to `{"type": "any"}` (an object, not the bare string `"any"`) to stop the model returning text: it forces a tool call even when finished and can loop forever. It is also unsupported on some current models: on Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, `any` and `tool` return a 400 error (use `auto` with strict tool use or structured outputs instead), and on any model they are not supported with manual extended thinking (`thinking: {type: "enabled"}`) and result in an error (use `auto` or `none`). [1.1]
- A `switch`/`if` on `stop_reason` that handles only `tool_use` and `end_turn`, with everything else silently treated as done. [1.1]
- Tool executed but its result not appended, or appended without the matching assistant turn. [1.1]

**Exam answer vs current practice**
- Exam keys only `tool_use` and `end_turn`. The live Messages API returns exactly seven values: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal` and `model_context_window_exceeded` (confirmed against Anthropic's docs on 2026-10-14; in streaming, `stop_reason` is null in `message_start`). Safety classifiers return `refusal` as a normal HTTP 200 response, not an error, on Claude Fable 5.1, Fable 5, Opus 5.5, Opus 5, Sonnet 5.5 and Haiku 5.5 (the guide names only Fable 5, which is now a legacy model); refusal details are in `stop_details`. Build for the full set; answer the exam with the two. [1.1, QR]

---

## 1.2 Multi-Agent Orchestration

**Rules**
- Use hub-and-spoke: one coordinator decomposes the task, selects subagents, passes context, aggregates results, handles errors and routes all information. Subagents return to the coordinator only. [1.2]
- Route every inter-subagent exchange through the coordinator, for observability, uniform error handling and controlled information flow. This is a design choice, not a platform limit: in current Claude Code, subagents with the `SendMessage` tool can message other named agents in the session, and agent-team teammates (experimental) message each other directly. [1.2]
- Assume subagents inherit nothing: not the coordinator's system prompt, history, other subagents' results, or any shared memory. Each invocation is independent of earlier ones. [1.2]
- Select subagents per query; do not push every request through the full pipeline. [1.2]
- Partition scope across subagents so they do not duplicate work (distinct subtopics or source types). [1.2]
- Run an iterative refinement loop: evaluate the synthesis for gaps, re-delegate targeted queries, re-synthesise until coverage is sufficient (with a maximum iteration count). [1.2]
- Decompose broadly enough to cover the whole topic; the exercise standard is at least five distinct subtopics for a broad topic. [1.2]
- When output is incomplete in *scope*, trace the fault to the coordinator's decomposition first, not the subagent that produced the output. [1.2]
- Keep the coordinator delegating and aggregating; a coordinator doing specialist work itself is a smell. [GL]
- Justify multi-agent designs: prefer specialists with small tool sets over one large agent, but use a simpler pattern when it suffices. [QR, GL]

**Anti-patterns to catch in review**
- In a design that has chosen hub-and-spoke, subagents messaging each other directly (for example via `SendMessage`), or a shared global store used as a back channel. [1.2]
- Subagent prompts that refer to "the above", "as discussed", or results they were never given. [1.2]
- Every query routed through every subagent regardless of need. [1.2]
- Two subagents given overlapping scope or the same sources. [1.2]
- Single-shot delegation with no coverage check. [1.2]
- Fixing a coverage gap by adding subagents or better search queries while the decomposition stays narrow. [1.2]

**Exam answer vs current practice**
- (Guide/exam answer: subagents never communicate except via the coordinator, "never, for any reason"; current: hub-and-spoke is still the default, with subagents reporting results back to the main agent, but the absolute is an exam simplification.) In current Claude Code, subagents that Claude named when it spawned them can message each other (`SendMessage`), and in agent teams (experimental, off by default) teammates message each other directly. A subagent can also spawn subagents of its own, by default (v2.1.219 and later) up to three layers below the main conversation; `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` sets the limit, and `1` stops subagents spawning any. (GL says "there is no agent-to-agent handoff primitive in the Agent SDK"; no primitive called "handoff" was found in the docs, but `SendMessage` lets agents message each other.) Confirmed against Anthropic's docs on 2026-10-14. [1.2, GL]

---

## 1.3 Subagent Invocation and Context Passing

**Rules**
- Make sure the coordinator can reach the delegation tool (`Task` in exam terms, `Agent` in current Claude Code): `Agent` must not be named in `disallowedTools` or left out of a restrictive `tools` list (for example agent frontmatter `tools`), and a coordinator that is itself a subagent must sit above the spawn-depth limit. Listing it in `allowedTools` is not required: `allowedTools` only auto-approves tools, and `Agent` needs no approval. When a coordinator will not delegate, Anthropic's documented fix is in the prompt: name the subagent in the prompt and write a clear `description` saying exactly when to use it. Note that with the `claude_code` preset on Opus 5, Claude Code adds a system-prompt line telling Claude not to call `Agent` unless asked; the tool stays available. (Guide/exam answer: a coordinator that will not delegate is missing `Task` from `allowedTools`, not suffering from a weak prompt; current: the reverse, as above.) [1.3, GL]
- Define each subagent with a description (used for routing), instructions, and a scoped `tools` list. Keep tool sets small and role-focused; the guide contrasts 4–5 tools with 18, where selection reliability degrades. [1.3, QR, GL]
- Pass complete prior findings into the subagent's prompt, in full. [1.3]
- Pass findings as structured data that separates content from metadata (claim, source URL, document name, page number, confidence, retrieved-by). Never strip metadata before synthesis. [1.3]
- Write subagent prompts as goals plus quality criteria, not step-by-step procedures. [1.3]
- Spawn independent subagents in parallel: several delegation tool calls in one coordinator response, not one per turn. [1.3]
- Use fork to explore divergent approaches from a shared baseline; use resume to continue the same line of work. [1.3]
- When a downstream agent produces unsourced claims while upstream agents return sources, fix the coordinator's context passing; do not rewrite the synthesis prompt or give the synthesis agent search tools. [1.3]

**Anti-patterns to catch in review**
- Coordinator config that names `Agent` in `disallowedTools`, or leaves it out of a restrictive `tools` list, while `agents` are defined. (`Agent` missing from `allowedTools` alone does not block delegation.) [1.3]
- A subagent with a broad or unscoped tool list, or one agent carrying many tools "for simplicity". [1.3, QR]
- Coordinator code that passes `finding.claim` (or summarised text) rather than the full findings object. [1.3]
- Independent subagents awaited one after another across turns. [1.3]
- Procedural, numbered-step subagent prompts with no stated goal or acceptance criteria. [1.3]

**Exam answer vs current practice**
- Name: exam says Task tool; Claude Code renamed it `Agent` in v2.1.63 (28 February 2026), and existing `Task(...)` references still work as aliases. The Agent SDK emits `Agent` in `tool_use` blocks but still lists `Task` in the `system:init` tools list, so detection code should match both. [1.3]
- `allowedTools`: (Guide/exam answer: a hard gate on delegation; current: an auto-approve list only.) In the Agent SDK, `allowedTools` / `allowed_tools` auto-approves the tools it names and "does not restrict Claude to only these tools". `Agent` needs no approval, so it runs whether or not it is listed, and leaving it out does not send spawns to the permission callback (`canUseTool`). The guide's claim that omitting `Agent` gets every spawn denied in an unattended run is wrong. What actually removes delegation: `disallowedTools` naming `Agent`, a `tools` list that leaves it out, or, for a coordinator that is itself a subagent, the spawn-depth limit `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` (it counts layers below the main conversation and cannot go below 1, so it never removes delegation from the main agent). [1.3]
- Fork vs resume: exam treats them as two alternatives. Current SDK: fork is a modifier on resume (`resume=session_id, fork_session=True`); without `fork_session` the same call appends. CLI `--fork-session` only works alongside `--resume` or `--continue`. The real choice is append versus branch. [1.3, 1.7]
- AgentDefinition fields: 1.3 lists "System prompt"; GL says the field is `prompt`, not `systemPrompt`. GL is right: the required fields are `description` and `prompt` (the agent's system prompt); `tools` is optional, and if omitted the subagent inherits every tool available to subagents. [1.3, GL]

---

## 1.4 Workflow Enforcement and Handoff

**Rules**
- If a single failure would cause financial loss, a security breach or a compliance violation, enforce the rule in code (hook, prerequisite gate, code check), not in the prompt. [1.4]
- Use prompt guidance only for low-stakes preferences (formatting, style, output order). [1.4]
- Implement prerequisite gates as session state checked in the tool handler or a hook: e.g. `process_refund` returns an error until `get_customer` has returned a verified customer ID in this session. The error message should tell the model what to do first. [1.4]
- Test a gate by instructing the agent to skip the prerequisite and confirming the gate blocks it. [1.4]
- Decompose multi-concern requests into distinct items, investigate them in parallel with shared context, and answer all of them in one unified resolution. [1.4]
- When escalating to a human, produce a self-contained handoff: customer ID, conversation summary, root cause analysis, refund amount (exact figure, if applicable), recommended action. Assume the human has no transcript. [1.4]
- Never fail silently: an agent that cannot finish produces a structured handoff, not a generic error. [QR]
- Hand off to a person on the three triggers in module 5.2 (an explicit request for a person, a policy gap, no progress after a genuine attempt); for genuine ambiguity, such as several matching records, ask for a distinguishing detail instead. Gate destructive operations in code. In a pipeline, a calibrated classifier score below a per-category threshold can route an item to human review; the agent's self-reported confidence never should. [QR, 5.2]
- To enforce rules on subagent spawning, use a PreToolUse hook on the `Agent` tool (it can deny or rewrite the spawn); SubagentStart cannot block. [1.4]
- Use SubagentStop to send a subagent back to work when its output fails schema validation: exit code 2 with a stderr message, or `{"decision": "block", "reason": "..."}`; either way the message is delivered to the subagent as its next instruction. It is not an absolute gate: after eight consecutive continuations Claude Code overrides the next block and ends the turn (raise with `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`; the count resets when Claude calls a tool), so validate the final output in code as well. `hookSpecificOutput.additionalContext` also keeps the subagent running, but it shows as hook feedback rather than a hook error. To let the subagent stop, exit 0 with neither `decision` nor `additionalContext`. [1.4]
- Prefer reshaping a subagent's output in the coordinator. A PostToolUse hook can replace the result Claude sees (`updatedToolOutput`, which works for all tools), but that hides the real output from Claude. [1.4]
- Put per-subagent policy in that subagent's frontmatter hooks; they run only while that subagent is active. Frontmatter `hooks` are ignored for plugin subagents, and project-subagent frontmatter hooks run only after the workspace trust dialog is accepted (a `-p` session does not count as accepting it). [1.4]

**Anti-patterns to catch in review**
- "Always verify X before Y" in a system prompt as the only control on a money, identity or compliance action. [1.4]
- Few-shot examples or "stronger wording" offered as the fix for a measured compliance failure rate (e.g. the 8% case). [1.4]
- A routing classifier proposed to fix behaviour inside one agent's execution sequence. [1.4, GL]
- Handoff payloads missing customer ID, amount or recommended action, or saying "see conversation above". [1.4]
- Multi-concern requests answered only for the first item. [1.4]
- A SubagentStart hook expected to block spawns (it cannot block; its event-specific output is `additionalContext`; block with PreToolUse on `Agent`). [1.4]
- A PostToolUse hook that silently reshapes a subagent's result: possible via `updatedToolOutput`, but it hides the real output from Claude. [1.4]

**Exam answer vs current practice**
- SubagentStart/SubagentStop are flagged "Beyond the guide": useful background, not tested; the guide's appendix scopes SDK hooks to PostToolUse and tool-call interception. (Guide: SubagentStop blocks only via exit code 2 and has no `decision` field; current: SubagentStop uses the same decision control as Stop, so `decision: "block"` with a `reason` also works.) (Guide: no hook field rewrites a tool result in place; current: PostToolUse `updatedToolOutput` does, for any tool, though it only changes what Claude sees and cannot undo side effects.) Checked against the hooks reference on 2026-10-14. [1.4]
- QR lists four handoff fields (no refund amount); 1.4 and GL require five. Use five. [1.4, QR, GL]

---

## 1.5 Agent SDK Hooks

**Rules**
- Use PreToolUse to block, modify or redirect a call before it runs (thresholds, prerequisite gates, approval routing). [1.5]
- Use PostToolUse to normalise, validate, redact or audit tool results before the model sees them (timestamps to ISO 8601, status codes to readable strings, currency to a fixed decimal format with code). [1.5, GL]
- Never use PostToolUse to prevent an action: the tool has already run. A PostToolUse `decision: "block"` or exit code 2 does not stop the loop; it only adds feedback beside the result and Claude continues. To halt, return `"continue": false`. Neither undoes the side effect. [1.5]
- Requirement must hold 100% of the time → hook (deterministic). Preference where deviation is acceptable → prompt (probabilistic). Decide by the cost of a single failure, not by whether the prompt is "good enough". [1.5]
- Do not leave format normalisation of heterogeneous tool outputs to the model. [1.5]
- Record prerequisite state with a PostToolUse hook on the prerequisite tool (e.g. `aml_check`) and check it in a PreToolUse hook on the guarded tool (`transfer_funds`). [1.5]
- Archive the full transcript in a PreCompact hook when detail must survive compaction. [1.5]
- Words in a requirement such as "guaranteed", "must always", "enforce", "compliance", "audit" point to hooks, not prompts. [QR]

**Anti-patterns to catch in review**
- A PostToolUse hook that "flags" or queues a completed non-compliant action as the compliance control. [1.5]
- Prompt text asking the model to convert dates or decode status codes from mixed sources. [1.5]
- A deny hook that only logs and lets the call proceed. [1.5]
- Hooks added for pure formatting preferences (unnecessary overhead). [1.5]
- New code using `updatedMCPToolOutput` (deprecated; use `updatedToolOutput`, which works for all tools). [1.5]

**Exam answer vs current practice**
- Exam frames PreToolUse/PostToolUse only. Current return fields, confirmed against Anthropic's docs on 2026-10-14: PreToolUse `permissionDecision` of `allow`/`deny`/`ask`/`defer` plus `updatedInput`, inside `hookSpecificOutput`; PostToolUse `updatedToolOutput` (all tools; `updatedMCPToolOutput` is MCP-only and deprecated). `defer` is honoured only in non-interactive `-p` runs. For built-in tools, an `updatedToolOutput` value that does not match the tool's output schema is ignored. [1.5]
- PreCompact is "Beyond the guide" but the page says its practice bank has tested it since July. In the Agent SDK, `PostCompact` is available in TypeScript only; the Python SDK does not have it. [1.5]
- (QR: hooks "cannot be bypassed by prompt injection"; current: none of Anthropic's hooks pages checked on 2026-10-14 makes that claim.) The documented property is narrower: command hooks are deterministic, and a PreToolUse deny holds in every permission mode, including `bypassPermissions`. Known gaps: a typed `/skillname` skips PreToolUse (use UserPromptExpansion); a file changed through `Bash` skips an `Edit|Write` PostToolUse (use FileChanged); `prompt` and `agent` hook types are judged by a Claude model. Test each hook. [QR]

---

## 1.6 Task Decomposition Strategies

**Rules**
- Choose a fixed sequential pipeline (prompt chaining) when steps are known in advance and inputs are structured: multi-file code review, document extraction, compliance checks. [1.6]
- Choose dynamic adaptive decomposition when scope is unknown: legacy exploration, security audits, research, debugging unfamiliar systems. Re-plan as dependencies emerge. [1.6]
- Match the pattern to the task, not to what sounds more sophisticated. [1.6]
- Use parallel orchestration for independent subtasks and sequential when each step needs the previous output. [QR]
- When many items are reviewed, use multi-pass: one local pass per item, then a separate cross-item integration pass (data flow, API consistency, pattern consistency). [1.6]
- Treat attention dilution as architectural: a bigger model, bigger context window or better prompt is not the fix. [1.6]
- If batching, still add a cross-batch integration pass. [1.6]

**Anti-patterns to catch in review**
- One prompt reviewing 10+ files at once. [1.6]
- Review output with detailed findings for early items and thin findings for later ones, or the same pattern flagged in one file and passed in another. [1.6]
- Batches of N files with no integration pass. [1.6]
- A fixed pipeline applied to open-ended investigation, or adaptive decomposition applied to a stable extraction job. [1.6]

**Exam answer vs current practice**
- No current-practice note on this page. Ambiguity: 1.6 defines attention dilution as too many *items* in one pass; GL defines it as one agent holding too many *concerns* (instructions and tools). Both lead to decomposition; treat both as valid symptoms. [1.6, GL]

---

## 1.7 Session State and Resumption

**Rules**
- Resume when prior context is still valid and files have not changed materially. [1.7]
- Fork when comparing divergent approaches from one shared analysis. [1.7]
- Start fresh with an injected structured summary when tool results are stale (files edited, dependencies updated) or the history is cluttered. [1.7]
- After changes, name the changed files in the summary and re-analyse only those (targeted re-analysis), not the whole codebase. [1.7]
- Do not "resume and re-read the changed files" as the fix: stale results stay in history and can still steer reasoning. [1.7]
- Do not fork to escape stale context: the fork inherits it. [1.7]
- Write summaries as conclusions (files, issues, severity, recommendations), not raw tool output. [1.7]
- Signals of stale context: repetition, contradiction of earlier statements, ignoring recent tool results. The fix is a curated fresh start, not more context. [QR, GL]

**Anti-patterns to catch in review**
- Long-running agents that resume across code changes with no freshness check. [1.7]
- Session handover notes that paste raw tool output rather than findings. [1.7]
- Full re-exploration of a large codebase when a few files changed. [1.7]

**Exam answer vs current practice**
- `--resume` only resumes existing sessions (by ID or name, or via an interactive picker); it never creates one, and an unknown ID exits with code 1. Name a session with `--name`/`-n` at start or `/rename` mid-session; `-c`/`--continue` resumes the most recent conversation in the current directory, but skips `-p`, Agent SDK and `/loop` sessions unless it is itself run with `-p`. Confirmed against Anthropic's docs on 2026-10-14. [1.7]
- Fork is set beside resume, not instead of it (see 1.3). [1.7]

---

## 3. Decision rules

| Situation | Choose | Over | Why |
|---|---|---|---|
| Deciding whether the loop continues | `stop_reason` check | Text checks, phrase parsing, iteration caps | Deterministic signal [1.1] |
| Agent exits early on complex tasks | Fix `stop_reason` handling | Raising the cap | Caps address runaway, not early exit [1.1, QR] |
| Runaway agent risk | Iteration cap as safety net | No bound | Bound cost; never primary control [1.1, QR] |
| Need flexibility, unexpected situations | Model-driven tool choice | Hard-coded decision tree | Adapts to unmapped cases [1.1, QR] |
| Several agents must cooperate | Hub-and-spoke via coordinator | Direct peer messaging | Observability, error handling, controlled flow; a design choice, since current Claude Code allows peer messaging (`SendMessage`, agent teams) [1.2] |
| Report misses whole categories | Fix coordinator decomposition | Better search, more subagents | Subagents only cover what they are assigned [1.2] |
| Subagent needs prior results | Pass full, structured context | Assuming shared memory | Subagents are isolated [1.2, 1.3] |
| Synthesis lacks citations | Pass content plus metadata | Prompting synthesis to cite; giving it search tools | It cannot cite what it never received [1.3] |
| Independent subtasks | Parallel spawning in one response | One spawn per turn | Latency [1.3, QR] |
| Coordinator will not delegate | Name the subagent in the prompt and write a clear `description`; check `Agent` is not in `disallowedTools` or missing from a restrictive `tools` list | Adding `Agent` to `allowedTools` | `allowedTools` only auto-approves, and `Agent` needs no approval; Anthropic's documented fix is in the prompt (guide/exam answer: add `Task` to `allowedTools`) [1.3, GL] |
| Money, identity or compliance rule | Hook or prerequisite gate | Stronger prompt, few-shot, routing classifier | Single failure is unacceptable [1.4, 1.5] |
| Style or format preference | Prompt guidance | Hook | Deviation is tolerable [1.4, 1.5] |
| Block an action | PreToolUse | PostToolUse | Post runs after the side effect, and its "block" only adds feedback; `"continue": false` halts but undoes nothing [1.5] |
| Mixed tool output formats | PostToolUse normalisation | Model-side conversion | Consistency every time [1.5] |
| Escalate to a human | Self-contained structured handoff | Pointer to transcript | Human has no transcript [1.4] |
| Routing an item to human review in a pipeline | Calibrated classifier score under threshold | Agent's self-reported confidence | Self-confidence is poorly calibrated; for customer hand-offs use the three triggers in 5.2 [QR] |
| Known, stable steps | Fixed pipeline / prompt chaining | Dynamic decomposition | Consistency, easy debugging [1.6] |
| Unknown scope | Dynamic adaptive decomposition | Fixed pipeline | Must adapt to findings [1.6, QR] |
| Many files to review | Per-file passes + integration pass | Single pass, bigger model, batches alone | Attention dilution [1.6] |
| Continue unchanged work | Resume | Fresh start | Full history still valid [1.7] |
| Compare two approaches | Fork (resume + fork flag) | Plain resume | Branch leaves the original intact [1.3, 1.7] |
| Files changed since last session | Fresh start + summary + targeted re-analysis | Resume and re-read; fork; full re-exploration | Stale tool results persist in history [1.7] |
| Transient failure | Retry with original, failed output and specific error | Blind retry | Gives the model what went wrong [QR] |
| Partial results available | Graceful degradation with metadata | Returning nothing | Partial beats none [QR] |

---
