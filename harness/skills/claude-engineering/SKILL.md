---
name: claude-engineering
description: Claude engineering standards for designing, building or reviewing anything that calls Claude or another LLM - agent loops, multi-agent orchestration and subagents, Agent SDK hooks, tool and MCP server design, tool_choice, structured output and JSON schemas, validation and retry loops, batch jobs, prompt caching, context management, escalation, human review and confidence calibration, provenance in research pipelines. Also the detailed reference for Claude Code configuration (CLAUDE.md, rules, skills, subagents, hooks, settings, CI).
when_to_use: Use when writing or reviewing code that uses the Anthropic API, Agent SDK, MCP, or a local LLM (for example a local-model client behind a shared queue); when designing prompts, tool schemas or agent pipelines; or when you need the exact current behaviour of a Claude Code feature.
---
# Claude engineering

Distilled from the Claude Certified Architect (Foundations) curriculum (claudecertificationguide.com, as read on 2026-10-14) and corrected against Anthropic's docs. Where the two differ, the corrected current fact is what you build to; the exam answer is noted only for context.

## How to use this skill
1. Read the checklist below for the area you are working in.
2. Open the matching reference file for rules, anti-patterns and decision tables. Read only the file you need.
3. The domain references have been corrected inline against Anthropic's docs; where the guide's exam answer differs, both are shown and the current fact is marked.
4. Before relying on an exact API field, flag, limit or model ID, search `references/verification.md` for it (Grep the name; the file is large, so do not read it whole). If it is not marked CONFIRMED there, check the live docs before using it. APIs change; these checks are dated 2026-10-14.

| Working on | Reference |
|---|---|
| Agent loops, orchestration, subagents, Agent SDK hooks, handoffs, sessions | `references/domain-1-agentic-architecture.md` |
| Tool definitions, tool errors, tool_choice, MCP servers and config, built-in tools | `references/domain-2-tool-design-mcp.md` |
| CLAUDE.md, rules, skills, commands, plan mode, CI/headless Claude Code | `references/domain-3-claude-code-config.md` |
| System prompts, few-shot, structured output, validation/retry, batch, multi-pass review | `references/domain-4-prompt-engineering.md` |
| Context windows, caching, escalation, error propagation, long sessions, human review, provenance | `references/domain-5-context-reliability.md` |
| Exact current Claude Code behaviour (paths, frontmatter, hooks, settings, CLI flags) | `references/claude-code-current-spec.md` |
| Which guide claims were checked against the docs, and corrections | `references/verification.md` |
| The plan template, review loop and severity scale the setup and audit skills use | `references/working-practice.md` |

## Checklists

### Agent loop [1.1]
- Loop on `stop_reason`: continue on `tool_use`; finish on `end_turn`; handle every other value explicitly (for example `max_tokens`, `pause_turn`, `refusal`, `stop_sequence`) rather than treating it as done.
- Current models can return `stop_reason: "refusal"` on an ordinary HTTP 200 response. Read `stop_details` and decide (retry on a fallback model, or surface it); never parse it as a normal answer.
- Append the assistant turn and every tool result to the history before the next call.
- Never decide "finished" by parsing the text, and never use an iteration cap as the stopping rule. A cap is a logged safety net only.

### Orchestration and subagents [1.2–1.4, 1.6]
- Default to hub and spoke: a coordinator decomposes, delegates, aggregates and checks coverage, and results flow through it. (Peer messaging between agents exists in Claude Code, but routing through the coordinator keeps the flow auditable.)
- In the Agent SDK and Claude Code, `allowedTools` only auto-approves tools; it neither restricts tools nor enables delegation. Restrict with `disallowedTools` or a `tools` list. If a coordinator will not delegate, name the subagent in the prompt and sharpen the subagent's `description`.
- Each subagent gets a self-contained brief and a focused, role-specific tool set. (The guide's rule of thumb is 4–5 tools per agent; Anthropic documents selection degrading past 30–50 tools and recommends tool search from about 10.)
- Pass findings between agents as structured data with source metadata, not prose.
- Use a fixed pipeline when the steps are predictable; dynamic decomposition only when they are not.
- Rules that must hold (approval before refunds, identity checks, destructive actions) are enforced in code or hooks, not in prompt text.
- Handoffs to a person carry a structured summary: who, what was asked, what was done, what is blocked, what is recommended.

### Tools and MCP [2.1–2.4]
- Each tool description (at least 3–4 sentences; Anthropic calls descriptions "by far the most important factor in tool performance") says what it does, when to use it, when not to, what each input means, caveats, and what it returns.
- Use service-prefixed tool names (`github_list_prs`), descriptive parameter names, `enum` for closed sets, and only the `required` fields that truly are. Consolidate related operations rather than one tool per action.
- Tool errors are structured: an error flag plus (a convention from the guide, not part of any spec) a category such as transient, validation, permission or business rule, whether it is retryable, and a human-readable message. A successful empty result is not an error.
- MCP: bad arguments (wrong format, out of range) are tool execution errors returned with `isError: true` so the model can correct itself; only an unknown tool, a malformed request or a server fault is a JSON-RPC protocol error (spec revision 2026-07-28).
- Make mandatory steps deterministic in code, not prompt wording. **Current fact, differs from the guide:** on Claude Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, forced `tool_choice` (`any` or `tool`) returns HTTP 400, and it also fails with an error on any model using manual extended thinking. Use `auto` with `strict: true` tools plus an explicit instruction, or structured outputs (not on Claude in Amazon Bedrock, or on Fable and Mythos models in a CMEK organisation: see Prompts and structured output below). Where forcing is still supported (for example Haiku 5.5, Opus 5), a forced call skips thinking. Model list as of 2026-10-14; see `references/verification.md`.
- Before building an MCP server, look for an existing maintained one. Use resources for catalogues the agent would otherwise discover by repeated tool calls.
- Never put secrets in `.mcp.json`; use `${VAR}` expansion: in `headers` for remote `http` servers, in `env` for local stdio servers. An unset variable does not stop the config loading (Claude Code warns and uses the literal text), so check the variables are set. In a remote server's `url`/`headers`, a documented set of credential variables (such as `ANTHROPIC_API_KEY`) reads as empty, so give MCP secrets their own variable names.

### Prompts and structured output [4.1–4.4]
- Explicit criteria: what to report, what to skip, severity definitions, an example per level. No "be conservative".
- Few-shot: 3–5 examples in `<example>` tags (Anthropic's guidance; the guide says 2–4), covering the hard or ambiguous cases, with the reasoning shown.
- Structured output: a schema alone does not guarantee conformance. Use `strict: true` on tools or `output_config.format` (structured outputs); strict needs `additionalProperties: false` on every object and supports a subset of JSON Schema. Output can still be cut off at `max_tokens` or be a refusal, so check `stop_reason` before parsing. On Claude in Amazon Bedrock (any model), and for Claude Fable and Mythos models in a CMEK organisation, strict tools and structured outputs are not available (as of 2026-10-14): use prompt instructions and validate everything in code.
- Optional fields: `"type": ["string", "null"]` and a parent `required` array, not `nullable: true` or per-property `required`. Include "other"/"unclear" in enums.
- Current models: omit the sampling parameters. On models released after Claude Opus 4.6, `top_k` is rejected at any value, `temperature` other than 1.0 and `top_p` below 0.99 return 400 (on Haiku 5.5, any `top_p` other than exactly 0.99, including 1), and Haiku 5.5 rejects `temperature` and `top_p` sent together. Do not prefill the assistant turn (400 on current models); use instructions or structured outputs instead.
- Validate semantics in code after parsing (cross-field rules, ranges, consistency). Retry with the specific error, the source and the previous output; cap retries; never retry "absent from source": route it to review.

### Batch and multi-pass review [4.5, 4.6]
- Batch only latency-tolerant work; plan on the worst-case processing window; prove the prompt on 5–10 items first; join results on a unique `custom_id`; resubmit only failures.
- Review generated work with an independent instance, never in the session that produced it. Review per unit, then one integration pass.

### Context, escalation and reliability [5.1–5.5]
- Keep a facts block (IDs, amounts, dates, decisions) carried verbatim; trim verbose tool output in the tool or a hook; summaries never replace the facts block.
- Prompt caching: the cached prefix is `tools`, then `system`, then `messages`; keep stable content first and nothing volatile before the last breakpoint (at most 4). Caching is opt-in (`cache_control`), prompts under the model minimum are silently not cached, and with caching `input_tokens` counts only tokens after the last breakpoint (total = cache read + cache creation + input).
- Long documents go at the top of the prompt and the question at the end.
- Current models (Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5) have 1M-token windows as of 2026-10-14; Claude Code auto-compacts near the limit, so keep the facts block and state file on disk, not only in the conversation.
- Rate limits: honour `retry-after` when present (the SDK already retries 429/5xx twice). A spend-cap 429 has no `retry-after` and will keep failing, so stop and report rather than retry.
- Escalate to a person on three triggers: an explicit request for a person (immediately, without trying first), a policy gap where the policy is silent, or no meaningful progress after a genuine attempt. A documented policy "no" is a refusal with the reason, not an escalation. Never escalate on sentiment or self-rated confidence.
- When a lookup matches several records, ask for a distinguishing identifier; never pick one heuristically.
- Errors propagate with type, attempted action, partial results and alternatives. Catch blocks never return "success".
- Before automating with confidence thresholds: measure accuracy per segment, calibrate the thresholds on labelled data, keep sampling high-confidence output, and send uncertain items to people first.

### Provenance and research [5.6]
- Every claim carries claim, source, excerpt and date through every stage, especially synthesis.
- Conflicting sources are shown side by side with dates; coverage gaps are stated.

### Local or self-hosted LLM (for example a local model behind a shared queue)
- The same patterns apply: schema-check every output, validate deterministically, retry with feedback, never let the model judge its own work alone.
- Follow that service's queue rules (your own `~/.claude/CLAUDE.md` may define them). If it allows one request at a time, "parallel" review passes run one after another there.
- Do not assume Anthropic-only features (tool_choice, strict schemas, Batch API, prompt caching) exist on the local server. Check its docs first, otherwise treat output as prompt-based JSON needing full validation.
