# Domain 5: Context Management and Reliability – Engineering Standard

**Exam weight:** 15% (from the guide's exam overview page, at claudecertificationguide.com: "Context Management & Reliability (15%)"; the Domain 5 pages themselves do not state it).
**Modules:** 5.1 Context window management · 5.2 Escalation and ambiguity · 5.3 Error propagation · 5.4 Codebase exploration · 5.5 Human review and calibration · 5.6 Information provenance.
**Sources (claudecertificationguide.com):** the six Domain 5 lesson pages (tagged [5.1] to [5.6]), the quick reference [QR], glossary [GL] and exercises page.
**Status of claims:** Technical claims checked against Anthropic's docs on 2026-10-14; corrections applied inline. Evidence: `references/verification.md`.

---

## 5.1 Context window management

**Rules**
- Pull transactional facts (amounts, dates, order or case IDs, statuses, stated customer expectations) into a structured "case facts" block, include it in every prompt, keep it outside the summarised history, and never summarise it. [5.1]
- In multi-issue sessions, give each issue its own entry in the facts layer so that summarising does not blend one issue into another. [5.1]
- When summarising to save context, summarise only narrative flow. Copy the facts block forward word for word. [5.1]
- Trim verbose tool results to the fields the task needs before they enter history, either in the tool itself or in a `PostToolUse` hook. Once untrimmed output is in history it is paid for on every later turn. [5.1] In both Claude Code and the Agent SDK, a `PostToolUse` hook replaces the result with `updatedToolOutput`, which works for all tools (`updatedMCPToolOutput` is MCP-only). The hook runs after the tool has executed, and telemetry records the original output. For built-in tools the replacement must match the tool's output schema or it is ignored. To prevent or reshape the call itself, use `PreToolUse` with `updatedInput`. (Checked 2026-10-14.)
- When aggregating long inputs (for example, several subagents' outputs for a synthesiser), put a "Key Findings Summary" first, then the detail under explicit section headers. Fix position effects through structure, not by telling the model to "pay attention to everything". [5.1]
- When a prompt carries long documents or inputs, place them near the top, above the query, instructions and examples, and put the query at the end; Anthropic reports that queries at the end "can improve response quality by up to 30 percent in tests". Source: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#long-context-prompting (the old long-context-tips path redirects there). Do not attribute "models process the beginning and end of long inputs reliably" ("lost in the middle") to Anthropic: its docs make no such statement. They say only that as token count grows, accuracy and recall degrade ("context rot"). (Checked 2026-10-14.) [5.1]
- Send the full conversation history the request needs on every call, because the API is stateless. Do not drop earlier turns selectively; use a facts block plus summarisation instead. [5.1] Current qualifier (2026-10-14): server-side compaction replaces older turns with a summary Claude writes on the server. It comes in two beta kinds, each with its own beta header, on Opus 4.6, Sonnet 4.6 and later models (not Haiku 4.5). Compaction on demand (header `compact-2026-09-04`, top-level `compaction` parameter): send the returned block first in `messages`, in place of the turns it summarises. Compaction at a token threshold (header `compact-2026-01-12`, a `compact_20260112` entry in `context_management.edits`): append the response as usual, and the API drops what came before the block. Either way you still send the history on every call. Context editing can also clear old tool results and thinking blocks.
- On the raw API, an input that exceeds the context window is rejected with HTTP 400 `invalid_request_error` ("prompt is too long"); nothing is dropped for you. If the input fits but input plus `max_tokens` does not, Claude 4.5 and newer models accept the request and, if generation reaches the limit, stop with `stop_reason: "model_context_window_exceeded"`. Manage history size before sending. (Checked 2026-10-14.)
- Make upstream agents return structured data (claim, source, relevance, date, method context), not reasoning chains or raw prose. [5.1]
- When using prompt caching, put static content first and volatile content after the last breakpoint. The cached prefix runs `tools` → `system` → `messages`, in that order, so tool definitions go in `tools` (not `system`) and any change to them invalidates the whole cache; static system instructions and reference documents go in the top-level `system` parameter. Hits need 100% identical prompt segments; the lookback window is 20 blocks. (Guide: put tool definitions in `system`; current: they belong in `tools`, ahead of `system`.) [5.1] To change the offered tools partway through a conversation without invalidating the cache, use `tool_addition` and `tool_removal` blocks in a mid-conversation `role: "system"` message (beta on the Claude API with the `inline-tools-2026-09-15` header, on the models that support mid-conversation system messages; checked 2026-10-14).
- Mark the cache in one of two ways: up to 4 explicit `cache_control` breakpoints, or automatic caching with a single top-level `"cache_control": {"type": "ephemeral"}` on the request body, which uses one of the 4 slots. Prompts below the model's minimum are silently not cached, even when marked. Minimums (Claude API, Claude Platform on AWS, Google Cloud and Microsoft Foundry, checked 2026-10-14): 512 tokens for Fable 5.1, Mythos 5.1, Opus 5.5, Opus 5, Sonnet 5.5, Fable 5, Mythos 5 and Haiku 5.5; 1,024 for Opus 4.8, Sonnet 5, Sonnet 4.6 and Sonnet 4.5 (deprecated); 2,048 for Mythos Preview and Opus 4.7; 4,096 for Opus 4.6, Opus 4.5 and Haiku 4.5. On Amazon Bedrock the minimum varies by model; see the Bedrock documentation. [5.1]
- Cache costs and lifetime (2026-10-14): reads cost 0.1× base input (0.05× on Opus 5.5 and Sonnet 5.5; 0.025× on Fable 5.1 and Mythos 5.1); writes cost 1.25× for the default 5-minute TTL and 2× for the 1-hour TTL (`{"type": "ephemeral", "ttl": "1h"}`). The 5-minute lifetime is refreshed at no cost on each use and is measured from the start of the request that writes or reads the entry. When mixing TTLs, put 1-hour entries before 5-minute entries. In Claude Code (2026-10-14) the main conversation gets a one-hour cache by default on a Claude subscription within plan usage. Everything else, subagents included, gets five minutes (apart from a few helper requests Anthropic controls server-side), and so does usage drawn from usage credits, an API key or a cloud provider. Set `promptCacheTtl` (main conversation) or `subagentPromptCacheTtl` (everything else) to `1h` to change it (Claude Code v2.1.242 or later). [5.1]
- With caching, `usage.input_tokens` counts only the tokens after the last cache breakpoint. Total input = `cache_read_input_tokens + cache_creation_input_tokens + input_tokens`; cost and context accounting must sum all three. Everything in the request counts toward the window: system prompt, every message (including tool results, images and documents) and tool definitions, and cached tokens still count. (Checked 2026-10-14.) [5.1]

**Anti-patterns to catch in review**
- A summariser prompt such as "summarise the conversation so far" with no protected facts block; a later turn says "your recent refund" instead of the amount and order number.
- Raw API or database responses (dozens of fields) appended straight to message history.
- A synthesis prompt that concatenates subagent outputs with no leading summary or headers.
- A history-truncation routine (keep the last N turns) with no facts block.
- Subagents returning their full chain of thought to a coordinator.
- Per-request dynamic text placed before the cached block; tool definitions that change between requests (they sit at the front of the cached prefix); a "cached" prefix shorter than the model's minimum cacheable length; 5-minute TTL entries placed before 1-hour entries.
- A `"role": "system"` message as the first entry in `messages`, followed directly by another user message, or used on a model that does not support it (for example Sonnet 5). (Guide: any `"system"` role inside `messages` is an anti-pattern; current: valid on most current models when it follows a user turn and precedes an assistant turn or ends `messages`, see below.)
- Token or cost accounting that reads only `usage.input_tokens` when prompt caching is on.

**Exam answer vs current practice**
- Caching: the guide says the exam tests only that caching exists and why (its out-of-scope list excludes "prompt caching implementation details (beyond knowing it exists)"; this exam-scope statement is the guide's and has not been checked against the official exam guide). The module still gives working mechanics "for real work". Build to the current mechanics in the rules above, checked against Anthropic's docs on 2026-10-14.
- Window size. (Guide/exam answer: the exam states no window size, and sizes are model-specific, "200K (Haiku 4.5) to 1M (Sonnet 5, Opus 5, Fable 5)" as at 14 August 2026; the exam-scope part is unverified. Current, 2026-10-14: every current model (Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5) has a 1M-token context window with 128K max output, by default and with no beta header. Sonnet 5, Opus 5 and Fable 5 are now legacy. 200K applies only to older models, among them Haiku 4.5 and Sonnet 4.5 (deprecated).) The window covers input plus output. In Claude Code, Fable 5.1, Fable 5, Sonnet 5 and later, Haiku 5.5, and Opus 4.7 and later run at 1M by default; Opus 4.6 and Sonnet 4.6 reach 1M only through the `[1m]` variant, depending on the plan. In an exam scenario, treat any stated figure as a limit set by that scenario.
- System role. (Guide/exam answer: "There is no `"system"` role for input messages in the Messages API"; `messages` takes user and assistant turns only. Current, 2026-10-14: a `"role": "system"` message inside `messages` is valid, with no beta header, on Fable 5.1, Mythos 5.1, Fable 5, Mythos 5, Opus 5.5, Opus 4.8, Opus 5, Sonnet 5.5 and Haiku 5.5. It must immediately follow a user turn (including one carrying tool results) and must either end `messages` or be followed by an assistant turn; it cannot be the first entry, and one followed directly by another user message returns a 400 error. It is not available on Sonnet 5.) Rule: instructions that apply from the start go in top-level `system`; a mid-conversation system message is valid on supported models and does not invalidate the cached prefix before it.
- Model ID: the guide's caching code sample uses `claude-sonnet-5`, which is valid but legacy (retirement not sooner than 30 June 2027). Use `claude-sonnet-5-5` in new examples.
- The guide's line on summarising is ambiguous. 5.1 says to use "case facts blocks and summarisation instead of truncation", while the quick reference marks "Summarise the conversation to save context" as wrong. The reconciled reading: summarisation is acceptable only alongside a verbatim facts block.

## 5.2 Escalation and ambiguity

**Rules**
- Escalate to a human on exactly three triggers: (1) the customer explicitly asks for a human; (2) a policy gap or exception, where the policy is silent; (3) no meaningful progress after a genuine attempt. [5.2]
- When a customer explicitly asks for a human, escalate in the first response, with no investigation and no "let me try first". The guide calls this absolute. [5.2]
- Treat a policy violation (the policy gives a documented "no") as a refusal with the policy explained, not as an escalation. Escalate only gaps. [5.2]
- Never escalate on sentiment or on the model's own confidence score: frustration does not track complexity, and self-reported confidence is poorly calibrated. [5.2]
- When a customer is frustrated but the issue is resolvable, acknowledge the frustration and offer the fix. Escalate only if they then repeat that they want a human. [5.2]
- When a lookup returns more than one matching record, ask for another identifier (email, phone, order number). Never pick by recency, activity or any other heuristic. [5.2]
- To fix poor escalation calibration, first add explicit criteria and few-shot examples to the system prompt, covering escalate, resolve, and the handoff format (customer ID, root cause, recommended action). Do this before building classifiers or sentiment pipelines. [5.2]

**Anti-patterns to catch in review**
- `if sentiment < x: escalate()` or `if self_confidence < 7: route_to_human()`.
- Handling an "I want a human" message that runs tools or diagnostics before handing off.
- `matches[0]`, `sort(by=last_active)` or similar applied to multiple customer matches.
- Escalation for an out-of-window refund (a violation), or improvised exceptions for a policy gap.
- A proposal to add a trained classifier when the system prompt has no escalation criteria.
- Handoff payloads that are free text with no customer ID, root cause or recommended action.

**Exam answer vs current practice**
- The guide presents its escalation rules as exam keys and gives no contrasting current practice. The rules are the guide's own; Anthropic's docs do not set them out (checked 2026-10-14). Its cited sources are:
  - "Customer support agent", https://platform.claude.com/docs/en/about-claude/use-case-guides/customer-support-chat (the guide's link has a doubled `docs/en/docs` path that redirects here). It gives no escalation rules, only an "escalation efficiency" evaluation metric (target 95% or higher).
  - "Handle approvals and user input" (Agent SDK), https://code.claude.com/docs/en/agent-sdk/user-input. It covers tool-permission requests and clarifying questions via the `AskUserQuestion` tool, both of which trigger the `canUseTool` callback.
- Apparent tension: 5.2 rejects confidence scores as triggers, while 5.5 uses field-level confidence for routing. The guide reconciles this only implicitly: 5.5 requires calibration against labelled data first. Read it as "never use raw self-reported confidence".

## 5.3 Error propagation

**Rules**
- Every subagent failure that reaches the coordinator carries four things: failure type (transient, validation, business or permission), what was attempted (tool, query, parameters, target), partial results gathered, and possible alternative approaches. [5.3]
- Never catch an error and return `{"results": [], "status": "success"}`. The guide calls silent suppression the worst anti-pattern. [5.3]
- Never end the whole workflow because one subagent failed. The coordinator assesses the failure and continues with partial results or a targeted recovery. [5.3]
- Report an access failure (timeout, connection error, 401, 429) differently from a valid empty result (the query ran and found nothing). Retry or recover the first; accept the second as the answer. [5.3]
- Retry transient failures locally inside the subagent (the exercise uses 3 retries with exponential backoff of 1s, 2s and 4s) and pass on only what cannot be fixed locally, with partial results attached. [5.3] When calling the Claude API through the official SDK, note that it already retries connection errors, 429s and 5xx errors twice with exponential backoff by default (`max_retries` in Python; `maxRetries` in TypeScript), honouring `retry-after` when present; do not stack a second unbounded retry loop on top of it. (Checked 2026-10-14.)
- On a 429, honour the `retry-after` header when it is present, but do not assume every 429 carries it. A Messages API 429 with `error.details.error_code == "enforced_spend_limit_reached"` (the monthly spend cap) never has `retry-after` and keeps failing, SDK retries included, until access resumes: stop and report it as a non-transient failure rather than retry. (Checked 2026-10-14.)
- "Alternatives" means options the coordinator could try next. Recovery already attempted ("retried twice") belongs under "what was attempted". [5.3]
- Synthesis output must carry coverage annotations: which areas are well supported, and which are limited or missing and why. [5.3]
- Never send a generic error ("search unavailable", "something went wrong"), even after retries are exhausted. [5.3]

**Anti-patterns to catch in review**
- `except Exception: return []`, or a tool that reports "no orders found" when the lookup service was down.
- A top-level handler that aborts a pipeline of N subagents on the first exception and discards the completed results.
- Retry loops wrapped around queries that succeeded but returned nothing.
- Error objects with only `message: "failed"`; partial results thrown away on timeout.
- A research report that simply omits a topic when its subagent failed.

**Exam answer vs current practice**
- Option D in the 5.3 practice scenario (backoff, then a generic status) is a distractor because the final status is generic. Backoff itself is endorsed for local recovery.
- Minor inconsistency in the source: the module's failure-type set is transient, validation, business and permission, while the quick reference uses `"network_timeout"` and `"validation_error"` as examples. The module also says access failures warrant "consider retry", but its exercise says they "should be retried". A permission failure "cannot be retried without authorisation changes".
- Rate limits. (Guide/exam answer, quick reference: on a 429, "Wait and retry (respect `Retry-After`)". Current, 2026-10-14: right only when the header is present; the spend-cap 429 has no `retry-after` and must not be retried.)

## 5.4 Codebase exploration

**Rules**
- Treat context degradation as an attention problem, not a token-limit problem. Its symptom is references to "typical patterns" instead of the specific classes, paths and chains found earlier. A bigger window does not fix it. [5.4]
- From the start of any long exploration, keep a scratchpad file of key findings (exact class names, file paths, dependency chains, critical findings), and read it before answering later questions. [5.4]
- Delegate verbose investigation to subagents with focused questions, and have them return structured summaries. The main benefit is context isolation, not parallelism. [5.4]
- When exploring in phases, summarise phase 1 findings and inject them into phase 2 subagents' starting prompts, so they do not repeat discovery from a cold start. [5.4]
- Use `/compact` proactively during long sessions to protect context quality, not only when the limit is reached. [5.4] Pass focus instructions (for example `/compact focus on the auth bug fix`), or put them under a `# Compact instructions` heading in the project CLAUDE.md. `/compact` reads the conversation it summarises, so compacting a large context is itself a large request; when continuity is not needed, `/clear` costs nothing. Use `/context` to see current usage. (Checked 2026-10-14.)
- For crash recovery, have each agent export a state manifest (explored paths, key findings, current phase, next steps, open questions) to a known location. On resume, load it and inject it into prompts. [5.4]
- Never restart a degraded session without first saving state. When context is stale or contradictory, start fresh and inject a summary. [5.4] [QR]
- For large codebases, use per-file passes followed by an integration pass, to avoid diluting attention. [QR]

**Anti-patterns to catch in review**
- A long session whose answers have drifted to generic descriptions; no scratchpad or findings file exists.
- The main agent reading dozens of files directly instead of delegating.
- Phase 2 subagent prompts with no phase 1 summary, or subagents that re-run the same searches.
- No manifest or checkpoint in an exploration job that runs for hours.
- Pre-loading the whole codebase into the initial context (distractor D in the practice scenario).
- Context-pressure signals ignored: repetition, contradicting earlier statements, ignoring recent information. [QR]

**Exam answer vs current practice**
- The guide describes `/compact` only as a summarising command for proactive use. It does not mention auto-compaction, `/context`, `/clear`, `/autocompact` or focus instructions. Current Claude Code has all of them (checked 2026-10-14): `/compact [instructions]` takes optional focus instructions; `/context` visualises current context usage; `/clear` starts a new conversation with empty context; `/autocompact` sets how full the window gets before Claude Code compacts automatically.
- The guide contradicts itself on cause. 5.4 says degradation "is not a token limit problem", but the glossary says it "signals that the context window has filled with verbose discovery output", and the quick reference says pressure signals mean "the window is too full or the context is stale". Treat it as fullness of verbose output, not hitting the hard limit.
- Context full. (Guide/exam answer, quick reference: "When the context window fills up, conversation history is lost — scratchpad files are not." Current, 2026-10-14: Claude Code compacts automatically as it approaches the limit, so a full window does not end the session. On native-1M models the default trigger is about 967K tokens, adjustable with `/autocompact`. Compaction replaces the verbatim conversation with a structured summary: full tool outputs and intermediate reasoning are lost. CLAUDE.md, auto memory, up to five of the files Claude read or edited (most recently modified first; a file over 5,000 tokens returns as a path only) and invoked skill bodies are reloaded; nested CLAUDE.md files and path-scoped rules are summarised away until their trigger file is touched again. On the raw API, an input that exceeds the window returns 400 "prompt is too long".) The guide's advice still stands: keep findings in files, because files survive compaction and restarts.

## 5.5 Human review and calibration

**Rules**
- Never decide to automate on aggregate accuracy. Measure accuracy by document type and by field before automating. [5.5]
- Calibrate field-level confidence against a labelled validation set (ground truth) for each field and document type before it drives routing. [5.5]
- Route by calibrated thresholds: above the threshold, automate with sampling; below it, send to human review; in the ambiguous zone, prioritise for review. [5.5]
- Run stratified random sampling across document type, confidence band and field, including high-confidence automated items, to measure accuracy over time and catch new error patterns. [5.5]
- Order the reviewer queue by uncertainty, dynamically: low confidence, ambiguous or contradictory sources, and historically weak document types come first. Never spread review evenly or work in arrival order. [5.5]
- Follow this order: segment accuracy, then calibrate, then set thresholds, then sample, and only then reduce review on segments with proven accuracy. [5.5]
- When monitoring, track error rates by type, not the overall rate. [QR]
- For weak categories, apply targeted fixes (better examples, a tighter schema). [QR]

**Anti-patterns to catch in review**
- A dashboard or sign-off that cites a single overall accuracy figure.
- `if confidence > 0.95: auto_accept()` with no calibration data behind 0.95.
- Sampling only low-confidence items, or no sampling of automated output at all.
- A FIFO review queue.

**Exam answer vs current practice**
- The guide gives no contrast here. Inconsistency in the source: the key concept says 97% "can hide 40% error rates", while the exam-trap text says "40% accuracy", and the table shows 45.2% accuracy at worst. The figures are illustrative.
- Cited source: the guide labels https://code.claude.com/docs/en/agent-sdk/structured-outputs as "Anthropic Structured Data Extraction Guide". The page is "Agent SDK: Get structured output from agents" and covers JSON Schema output validation in the Agent SDK, not document extraction, confidence calibration or human review (checked 2026-10-14). The calibration and review rules above are the guide's own.

## 5.6 Information provenance

**Rules**
- Every finding carries a structured claim-source record: claim, source URL, document name, relevant excerpt, and publication or data-collection date. All five fields are required. [5.6]
- Subagents emit findings in this structure from the start. The synthesis prompt explicitly requires every output claim to trace to a source. The final output has inline citations or a reference section. [5.6]
- Use structured mappings, not inline links, as the carrier between pipeline steps, because inline links do not survive synthesis. [QR]
- When credible sources conflict, report both values with attribution and dates, plus a possible explanation. Never take the newer one, average them, or pick the "more authoritative" one. [5.6]
- Check dates before calling a difference a contradiction. It may be a trend. [5.6]
- An analysis agent finishes its work with conflicts annotated (`conflictDetected`, values, context) and leaves resolution to the coordinator or consumer. [5.6]
- Separate well-established findings from contested ones, and keep the original characterisations and method context. [5.6]
- Format by content type: financial data as tables, news as prose, technical findings as structured lists. [5.6]

**Anti-patterns to catch in review**
- A synthesis that says "grew significantly" with no figure, source or date.
- Findings files with URLs but no dates or excerpts.
- Code or prompts such as "prefer the most recent source", or `avg(values)`.
- One source and three agreeing sources presented with equal confidence.
- A report written entirely as prose with financial comparisons buried in paragraphs.

**Exam answer vs current practice**
- The guide names its citation source "Prompt Engineering — Citation and Attribution" but links https://platform.claude.com/docs/en/build-with-claude/citations, which is "Citations (API feature)", not prompt-engineering guidance (checked 2026-10-14). The native Citations API lets Claude give detailed citations when answering questions about documents; it is GA and supported on all active models. It is a candidate carrier for claim–source provenance in Claude apps. The guide does not discuss it.
- In the 5.6 practice scenario, option A ("escalate to a human before including either figure") is a distractor. The body text nonetheless allows the coordinator to "escalate to a human analyst" after annotating, so escalation is not wrong in itself; blocking the report on it is.

---

## Decision rules

| Situation | Choose | Over | Why |
|---|---|---|---|
| Details lost over a long conversation | Persistent facts block, copied verbatim | Progressive summarisation; "preserve numbers" instructions | Summarising removes figures, dates and IDs [5.1][QR] |
| Findings missed in a long aggregated input | Key findings first, plus section headers | Prompt reminders to read everything | Position effects need a structural fix [5.1] |
| Prompt carries long documents | Documents at the top, query at the end | Query first, documents after | Anthropic's documented long-context placement; up to 30% better in its tests (2026-10-14) [5.1] |
| Tool returns 40+ fields | Trim in the tool or a `PostToolUse` hook | Keeping everything "in case" | Cost recurs on every turn [5.1] |
| History too long | Facts block plus summarised narrative | Selective truncation | The API is stateless; coherence breaks [5.1] |
| Static prompt reused | Cache the static prefix (stable `tools`, then `system`), dynamic content after the last breakpoint | Dynamic content first; changing tool definitions | The prefix (`tools` → `system` → `messages`) must match exactly to get a hit; prompts below the model minimum are not cached [5.1] |
| Counting tokens or cost with caching on | Sum `cache_read_input_tokens`, `cache_creation_input_tokens` and `input_tokens` | `input_tokens` alone | `input_tokens` covers only tokens after the last breakpoint (2026-10-14) [5.1] |
| Claude Code context nearly full | Save state to a file, then `/compact` with focus instructions, or `/clear` and inject a summary when continuity is not needed | Waiting for auto-compaction | Every compaction, manual or automatic, drops verbatim tool output and reasoning; a focused `/compact` keeps what you choose; files survive (2026-10-14) [5.4] |
| Customer says "I want a human" | Escalate immediately | Investigating first | Absolute rule [5.2] |
| Frustrated customer, simple issue | Acknowledge and resolve | Escalation on sentiment | Sentiment does not track complexity [5.2] |
| Policy silent on request | Escalate | Improvising an exception | No authority to decide [5.2] |
| Policy forbids request | Refuse and explain the policy | Escalating | A documented answer exists [5.2][QR] |
| Several customer matches | Ask for another identifier | Most recent or most active record | Privacy and wrong-account risk [5.2] |
| Poor first-contact resolution | Explicit criteria plus few-shot in the prompt | Classifier, sentiment, or confidence score | Proportionate first step [5.2] |
| Subagent timeout | Structured error context | Empty success; aborting the workflow; generic status | The coordinator needs data to recover [5.3] |
| Tool returned nothing | Check: valid empty means accept; access failure means retry or fall back | Treating them alike | Avoids missed retries and wasted ones [5.3][QR] |
| Transient failure | Retry locally, then propagate | The coordinator handling every retry | Keeps the coordinator simple [5.3] |
| API returns 429 | Honour `retry-after` if present (the SDK already retries twice); on `enforced_spend_limit_reached`, stop and report | Assuming every 429 has `retry-after`; an extra unbounded retry loop | The spend-cap 429 fails until access resumes (2026-10-14) [5.3] |
| Session drifts to "typical patterns" | Scratchpad file | A bigger window; restarting; pre-loading the codebase | An attention problem, not capacity [5.4] |
| Verbose exploration | Subagents returning structured summaries | The main agent reading everything | Context isolation [5.4] |
| Phase 2 of an investigation | Inject the phase 1 summary | A cold start | Prevents duplicated work [5.4] |
| Model contradicts itself | Fresh start plus injected summary | Carrying on | Stale context [QR] |
| Findings must survive a reset or crash | Scratchpad or state manifest on disk | Conversation history | Files survive resets [5.4][QR] |
| High overall accuracy, users report errors | Accuracy by type and by field | Trusting the aggregate | The aggregate hides weak segments [5.5][QR] |
| Automating high-confidence output | Calibrate, then threshold, then stratified sampling | A raw-confidence cut-off | Raw scores are uncalibrated [5.5] |
| Limited reviewers | Dynamic uncertainty-ordered queue | Even spread or FIFO | Review effort goes where it adds value [5.5] |
| Sources disagree | Show both with attribution and dates | Newest, average, or "most authoritative" | Picking one gives false certainty [5.6] |
| Citations lost after processing | Structured claim-source mappings | Inline links | Mappings survive synthesis [QR] |
| Mixed content types in a report | Tables, prose and lists by content type | One uniform format | Readability [5.6] |

---
