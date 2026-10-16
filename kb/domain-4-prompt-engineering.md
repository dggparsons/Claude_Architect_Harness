# Domain 4: Prompt Engineering & Structured Output – Engineering Standard

**Exam weight:** 20% (Exam Guide v1.0, July 2026, as reported on the exam-guide page of claudecertificationguide.com; not checked against Anthropic's docs).
**Modules:** 4.1 System Prompts with Explicit Criteria · 4.2 Few-Shot Prompting · 4.3 Structured Output with Tool Use · 4.4 Validation, Retry, and Feedback Loops · 4.5 Batch Processing Strategies · 4.6 Multi-Instance and Multi-Pass Review.
**Sources:** the Domain 4 lesson pages of claudecertificationguide.com (tagged [4.1] to [4.6]), its quick reference [QR], glossary [GL] and exercises page; the exam weight from its exam-guide page.
**Status of claims:** Technical claims checked against Anthropic's docs on 2026-10-14; corrections applied inline. Evidence: `references/verification.md`. Tags such as [QR] and [GL] mean the guide's quick reference and glossary. Exam facts and the guidance on confidence calibration are guide claims, not API facts; the API docs do not cover them.
**Current model IDs (2026-10-14):** `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1` (plus `claude-mythos-5-1`, limited access). The guide's examples use `claude-sonnet-5`, which is legacy but still available.

---

## 4.1 System prompts with explicit criteria

**Rules**
1. State categorical criteria: what to report, what to skip, and the exact trigger for each finding type (for example "flag a comment only when its claimed behaviour contradicts the code"). [4.1]
2. Never use vague filters such as "be conservative", "only report high-confidence findings" or "use your best judgement" as a precision control. They give the model no decision boundary. [4.1]
3. Define each severity level with a concrete code example, not a prose description. The quick reference suggests 2 to 3 calibration examples. [4.1][QR]
4. Put explicit criteria first and confidence-based routing second. Never use self-reported confidence as a substitute for criteria. [4.1]
5. When one category has a high false-positive rate, disable that category temporarily, rework it with criteria and examples, and re-enable it once precision is measured as acceptable. False positives in one category erode trust in every category. [4.1]
6. Measure false-positive rate per category on a fixed test set before and after a prompt change. The exercise uses a 25% threshold for disabling a category, but that figure is illustrative, not a standard. [4.1 exercise]
7. Structure a system prompt as: role and context; rules and constraints; output format; calibration examples. [QR]
8. Avoid conflicting instructions, and know which content belongs in the system prompt and which in user messages. [GL]

**Anti-patterns to catch in review**
- A prompt containing "be conservative", "high confidence only", "important issues", "use judgement" or similar, with no listed categories.
- Severity tiers defined only in adjectives ("could cause system failures").
- A review pipeline that adds a confidence threshold to fix false positives without defining what counts as a finding.
- All categories left live while one category has a known high false-positive rate.
- No per-category precision measurement, so nobody can say which category is noisy.

**Exam answer vs current practice**
- None stated for 4.1. XML tags to separate prompt sections are "genuine Anthropic guidance" but not examined. [GL]
- *System prompt placement.* (Guide: the system prompt sits above the message history and persists across all turns; current: the top-level `system` parameter remains the default, but mid-conversation `{"role": "system"}` messages now exist, with no beta header, on Fable 5.1, Mythos 5.1, Fable 5, Mythos 5, Opus 5.5, Opus 4.8, Opus 5, Sonnet 5.5 and Haiku 5.5, not on Sonnet 5. They take precedence over the top-level `system` field for the turns that follow them.) [GL]
- *Cost.* (Guide: system prompts are the most cost-effective control because one prompt shapes every request; current: an uncached system prompt is billed as regular input tokens on every call, and Anthropic's prompt-caching and prompting docs make no such cost claim. See caching under 4.2.) [QR]

## 4.2 Few-shot prompting

**Rules**
1. When detailed instructions already exist and output is still inconsistent, add few-shot examples rather than more instructions. [4.2]
2. Use few-shot examples for three problems: inconsistent format; inconsistent judgement on ambiguous cases; empty fields when the data is present in an unexpected structure (for example in narrative text rather than a table). [4.2]
3. Use 3 to 5 targeted examples: Anthropic's prompting guidance says "Include 3–5 examples for best results". Make them relevant, diverse and structured, and wrap each in `<example>` tags (several in `<examples>` tags). (Guide/exam answer: 2 to 4, with 0 to 2 having the largest effect and 4 to 8 rarely helping; current: 3 to 5.) [4.2][QR]
4. Each example shows its reasoning (why this choice over the plausible alternative), not just the input and output. Reasoning lets the model generalise. [4.2]
5. Aim the examples at the failing cases, include at least one boundary case, and show what *not* to flag as well as what to flag. [4.2][QR]
6. Place examples in the system prompt when they are fixed, or in the user message when they vary per request. Place them before the request. Fixed examples suit prompt caching, but caching is opt-in: add a top-level `cache_control` field (automatic caching) or block-level breakpoints. The cache covers the prefix `tools`, then `system`, then `messages`, so it is not limited to the system prompt, and prompts below a minimum length (512 to 4,096 tokens, depending on the model, as of 2026-10-14) cannot be cached. Cache reads cost 0.1× the base input price (0.05× on Opus 5.5 and Sonnet 5.5; 0.025× on Fable 5.1 and Mythos 5.1); cache writes cost 1.25× (5-minute) or 2× (1-hour) (prices as of 2026-10-14). Uncached content is billed as regular input tokens on every call. (Guide: examples in the system prompt bring "caching benefits"; current: only when caching is switched on.) [QR][GL]
7. Match the problem to the technique: format, judgement and narrative extraction call for few-shot examples; malformed JSON calls for tool_use schemas with `strict: true`, or `output_config.format` (plain tool_use does not guarantee a valid input; see 4.3); fabricated values for missing fields call for optional fields or fields whose type allows `null`; wrong tool choice calls for better tool descriptions first, then few-shot examples; a sum mismatch calls for a validation-retry loop. [4.2]

**Anti-patterns to catch in review**
- Bare input-to-output pairs with no reasoning.
- Fewer than 3 examples where output is still inconsistent (Anthropic recommends 3 to 5).
- Ten or more examples, or examples that all show the easy case (for example only tables, when the failures are in narrative text).
- "Add more instructions" or "add a confidence threshold" as the fix for inconsistent judgement.
- Few-shot examples used to stop fabrication of genuinely absent data. That is a schema problem.

**Exam answer vs current practice**
- Few-shot examples are not reported to cause fabrication. The guide says they *reduce* hallucination in extraction. Its own exercise expects that fabrication of missing data will **not** improve with few-shot examples. [4.2]
- *How many examples.* (Guide/exam answer: 2 to 4; current Anthropic guidance: 3 to 5.) For the exam, answer 2 to 4; in practice, use 3 to 5. [4.2][QR]

## 4.3 Structured output with tool use

**Rules**
1. For machine-consumed output, use tool_use with a JSON schema and `strict: true` on the tool, or `output_config.format` (`type: "json_schema"`) when you need the response itself in a fixed JSON shape. Only these two guarantee schema conformance: without `strict: true`, a tool call can carry wrong types (`"2"` instead of `2`) or omit required fields. Never rely on JSON requested in the prompt; it is for prototypes only. Structured outputs and strict tools are not available on Claude in Amazon Bedrock (any model, including Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5; only the legacy Bedrock integration for Opus 4.6 and earlier has them): there, use prompt instructions or a non-strict tool and validate in code. The same applies to Claude Fable and Claude Mythos models in a CMEK organisation, where structured outputs, including `strict: true`, are not available (CMEK page and the Fable 5.1 / Mythos 5.1 migration guide, checked 2026-10-14). [4.3][QR]
2. Choose `tool_choice` deliberately. It is an object with four modes: `{"type": "auto"}` (the default when tools are given), `{"type": "any"}` (must call one of the tools, Claude chooses which), `{"type": "tool", "name": ...}` (must call that tool) and `{"type": "none"}` (no tool calls; the default when no tools are given).
   - On Claude Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, `any` and `tool` return a 400 error (also on the token counting endpoint; the Fable 5.1 and Mythos 5.1 migration guide also names the Message Batches API, and for Opus 5.5 and Sonnet 5.5 the docs do not say, so do not send forced choices in batches). There, use `auto` with `strict: true` and a prompt instruction saying when to call the tool, or `output_config.format` (neither is available on Claude in Amazon Bedrock, or for Fable and Mythos models in a CMEK organisation: see rule 1). Mid-conversation `role: "system"` messages (see 4.1) are another way to steer tool use on these models: name the tool and say the call is required for this turn.
   - On any model with manual extended thinking (`thinking: {type: "enabled"}`), `any` and `tool` are not supported and result in an error; use `auto` or `none` there.
   - Haiku 5.5, Opus 5, Sonnet 5 and older models still accept forcing (without manual extended thinking). There, a forced call skips thinking; use a forced `tool` for one mandatory structure or step, and `any` when there are several extraction tools and the document type is unknown. Pair forcing with `strict: true`: forcing guarantees only that a tool is called, and `any` plus strict is the documented way to guarantee both a call and a valid input.
   - Use `auto` without strict only when a text reply is legitimately acceptable, and handle the text-only reply.
   (Guide/exam answer: forced `tool` for one structure, `any` for unknown document types, `auto` only when text is acceptable; current: forcing is rejected on the current non-Haiku models.) [4.3][QR]
3. On models that accept forcing, send the next request after a forced call with `auto` (or omit the parameter): `tool_choice` is a per-request parameter, and the guide warns that the model otherwise calls the same tool again and loops (the docs do not describe the loop). [4.3]
4. Make a field optional, or union-typed with null (`{"type": ["string","null"]}`) and absent from the parent's `required` array, whenever the source may lack it. A required field makes the model invent a value. Under strict tools or `output_config.format`, each type array counts toward the limit of 16 union-type parameters per request (as of 2026-10-14). [4.3][QR]
5. Add `"unclear"` to an enum for genuinely ambiguous evidence, and an `"other"` value paired with a detail string whose type allows `null` for categories you did not foresee. [4.3]
6. Use `enum` for constrained choices, give every property a `description`, and keep the schema flat where possible. Anthropic's reason for flattening is grammar-compile complexity under strict ("Deeply nested objects with optional fields compound the complexity"); the docs make no claim that nesting reduces extraction accuracy, as the quick reference implies. [QR]
7. Put normalisation rules in the prompt alongside the schema (ISO 8601 dates, decimal amounts without currency symbols). The schema enforces structure; the prompt enforces format. [4.3]
8. Never treat schema conformance as correctness. Schemas do not stop sums that fail to match, values placed in the wrong field, or fabricated values. Semantic validation (4.4) is still required. [4.3]
9. Use JSON Schema syntax: express "may be null" with a type array (`"type": ["string", "null"]`), not `nullable: true` (OpenAPI), and list required fields in a `required` array on the parent object, not as a boolean on each property. Anthropic's docs do not say whether `nullable: true` or a per-property `required: true` is rejected or silently ignored, so lint against both forms rather than relying on the API to reject them. (Guide: "An input_schema using either form is rejected"; current: the docs are silent, and the claim has not been tested against the live API.) [QR]
10. Meet strict mode's requirements: `additionalProperties: false` on every object; only the supported subset of JSON Schema (an unsupported feature returns a 400 error with details); at most 20 strict tools, 24 optional parameters and 16 union-type parameters per request (as of 2026-10-14). Even under strict, handle `max_tokens` truncation, refusals and drift in `enum` or `const` capitalisation, and keep the semantic validation layer. [4.3][4.4]

**Anti-patterns to catch in review**
- Every field listed in `required` in an extraction schema over variable source documents.
- `"nullable": true` or `"required": true` inside a property of an `input_schema`.
- `tool_choice: auto` (or no tool_choice) on a pipeline that assumes a tool call, with no handling for a text-only reply.
- A forced `tool_choice` (`any` or `tool`) sent to Opus 5.5, Sonnet 5.5, Fable 5.1 or Mythos 5.1 (it returns a 400 error), or to any model with manual extended thinking (it results in an error).
- A forced `tool_choice` carried over into follow-up turns, on models that accept forcing.
- Code that assumes schema-valid tool input without `strict: true` or `output_config.format`, or that assumes either is available on Claude in Amazon Bedrock (any model).
- Code that assumes `stop_reason == "tool_use"` without handling `max_tokens` (an incomplete `tool_use` block) or `refusal`.
- A strict schema with an object missing `additionalProperties: false`.
- A trailing assistant prefill, which returns a 400 error on every current model.
- `json.loads(response.text)` on a production path.
- A closed enum with no `unclear` or `other` value for messy real-world input.
- Code that trusts tool input once it parses, with no business-rule checks.

**Exam answer vs current practice**
- *Hierarchy.* (Guide/exam answer: two tiers, tool_use over prompt-based JSON, with tool_use said to eliminate JSON syntax errors entirely; current: plain tool_use returns a parsed object but does not guarantee a schema-valid input. `strict: true` on a tool definition (what Claude passes to your function) and `output_config.format` (what Claude says in its response) are the two ways to guarantee schema conformance.) The guide's appendix calls strict mode "strict mode for syntax error elimination"; it does more: tool input strictly follows the `input_schema`, the tool name is always valid, and types are exact (`2`, not `"2"`). [4.3][GL]
- *tool_choice modes.* (Guide/exam answer: three, `auto`, `any` and `tool`; current: four, adding `{"type": "none"}`, the default when no tools are passed. `any` and `tool` return a 400 error on Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, and on any model with manual extended thinking they are not supported and result in an error.) [4.3]
- *How strong the guarantee is.* (Quick reference: a forced tool "guarantees the response matches your schema" and the "schema is validated by the API", and tool_use "eliminates" malformed JSON, missing fields and extra fields; current: all three are wrong.) Forcing guarantees only that a tool is called. Without strict, a tool call can return wrong types or omit required fields, and extra fields are blocked only under strict with `additionalProperties: false`. Strict works by grammar-constrained sampling of the model's tokens, not by validating afterwards. Module 4.3's "constrains the shape" is the right reading. [QR][4.3][4.4]
- *Prefill.* Not examined. Current: a trailing assistant prefill returns a 400 error on every current model (Opus 5.5, Sonnet 5.5, Haiku 5.5 even with thinking off, Fable 5.1, Mythos 5.1). Older models still accept it: Opus 4.5, Haiku 4.5 (with thinking off) and the deprecated Sonnet 4.5. Replace it by purpose: for output format, `output_config.format`, or a tool with an enum for classification; for a preamble, a system-prompt instruction; for a continuation, a user message; for a context reminder, the user turn. On Claude in Amazon Bedrock (any model), where structured outputs are not available, use prompt instructions plus validation in code. (Guide: "the documented replacement is `output_config.format`"; current: that is one replacement among several.) [GL]
- *Sampling parameters.* Not examined. (Guide: `temperature`, `top_p` and `top_k` are all rejected with a 400 error on current models; current, for models released after Claude Opus 4.6: `top_k` is rejected at any value, and `temperature`/`top_p` only at non-default values.) `top_k` with any value returns 400; `temperature` other than 1.0 returns 400 (1.0, the historical default, is accepted for backwards compatibility); `top_p` below 0.99 returns 400 (on Haiku 5.5, any `top_p` other than exactly 0.99, including 1). Haiku 5.5 also rejects a request that sends both `temperature` and `top_p`. Separately, the Python SDK v1.0+ no longer defines the three parameters, so passing any of them, at any value, raises a `TypeError` before the request is sent (per the Opus 5.5 migration guide). Recommended: omit all three. [GL]

## 4.4 Validation, retry and feedback loops

**Rules**
1. On a validation failure, retry with three things: the original document, the failed extraction, and the specific validation error, stated as expected versus found. Never retry with "try again" or the same prompt alone. [4.4][QR]
2. Before retrying, classify the failure. Retry format mismatches, structural errors, misplaced values and arithmetic errors. Do **not** retry when the information is absent from the source, held only in an external document, or needs knowledge the model lacks. Return null (if the schema allows it) or send the item to a human. [4.4]
3. Cap retries. The quick reference says to escalate after repeated failures (">2 retries"), when confidence is below threshold, or when the interpretation is fundamentally wrong. [QR]
4. Build self-checks into the schema: `calculated_total` beside `stated_total` (plus a discrepancy flag), and `conflict_detected` booleans with both conflicting values extracted rather than one picked silently. [4.4]
5. Add a `detected_pattern` field to review findings. Log developer dismissals by pattern and refine the prompt for the patterns dismissed most often. [4.4]
6. Keep a semantic validation layer even when the schema is enforced. In Python, use Pydantic validators for cross-field rules (sums, date order) and turn `ValidationError.errors()` into per-field messages for the retry prompt. [4.4]
7. Validators return specific, actionable messages naming the field, the rule, and the expected and actual values. [4.4 exercise]

**Anti-patterns to catch in review**
- A retry loop whose follow-up message omits the source document, the prior output, or the error text.
- A retry on null or missing-field errors for data that is not in the source.
- An unbounded retry loop, or retries with no route to human review.
- "Validation" that only checks that the JSON parses.
- Pydantic removed because "tool_use already enforces the schema". Plain tool_use does not enforce it, and even strict mode does not check business rules.
- Extraction that silently picks one of two contradictory values.
- Review findings with no pattern tag, so dismissals cannot be analysed.

**Exam answer vs current practice**
- Current (confirmed 2026-10-14): the Python SDK's `client.messages.parse(..., output_format=Invoice)` returns validated Pydantic instances via `parsed_output`. The SDK sends the schema on the wire as `output_config.format`; the old `output_format` request parameter is deprecated in the API. In TypeScript, pass `zodOutputFormat()` to `client.messages.parse()` as `output_config.format`. This does not remove the semantic layer, and on Claude in Amazon Bedrock (any model) structured outputs are not available, so validate in code there. [4.4]
- (Guide: `strict: true` "guarantees schema-conformant inputs server-side"; current: confirmed in substance, through grammar-constrained sampling, with documented exceptions for `max_tokens` truncation, refusals and `enum` capitalisation, and only for the supported subset of JSON Schema.) [4.4]
- The quick reference says to send the "original prompt"; the module says the "original document". In practice include both the task and the source. [QR][4.4]
- The quick reference lists "missing field" as retryable. Module 4.4 says absent information is not. Read this as "a field the model omitted although the data is present". [QR][4.4]

## 4.5 Batch processing

**Rules**
1. Use the Message Batches API only for latency-tolerant work (overnight reports, weekly audits, bulk extraction). Keep blocking work (pre-merge checks, real-time review, anything user-facing) synchronous. [4.5][QR]
2. Design schedules around the 24-hour maximum, never the typical time. Work backwards from the SLA: SLA minus 24 hours is the buffer, and the submission cadence must fit inside it with margin. The guide's example: a 30-hour SLA leaves 6 hours, so submit every 4 hours, because 6 hours leaves no margin. [4.5]
3. Expiry applies to each request, not to the whole batch. After 24 hours the batch's `processing_status` becomes `ended`; requests not yet processed come back with result type `expired` (not billed), and requests that finished keep their results. There are four result types, read at `result.result.type`: `succeeded`, `errored`, `canceled` (the batch was cancelled before the request was sent to the model) and `expired`. Treat `errored`, `expired` and `canceled` as not done and resubmit them. Within `errored`, an `invalid_request_error` needs the request fixed first; other errors can be retried as they are. (Guide: "A batch that does not finish inside it comes back `expired`", and only `errored` and `expired` are named as failures.) [4.5]
4. Give every request a unique `custom_id` matching `^[a-zA-Z0-9_-]{1,64}$`. Results come back in any order, so always join on `custom_id`. Find failures by `custom_id` and resubmit only the failures, with a targeted change (chunk oversized documents, simplify the prompt, add few-shot examples for that format). Never resubmit the whole batch. [4.5]
5. Refine the prompt on a representative sample (5 to 10 documents covering formats and edge cases) before you submit the full batch. Each request's `params` are validated asynchronously and errors appear only when the batch ends, so also dry-run one request on the Messages API first. [4.5]
6. Batches accept tool use, multi-turn conversation histories, extended thinking and all server tools (web search, web fetch, code execution, MCP connectors, advisor and tool search). Server tools run their loop inside the batch item and can end with `stop_reason: "pause_turn"`; continue those in a follow-up request. Client tools end the item at `stop_reason: "tool_use"`, so a workflow that needs client-side tool execution mid-request cannot complete inside one batch item. Run that step synchronously, or split it into request, then local tool run, then follow-up request. Do not send a forced `tool_choice` in a batch to Opus 5.5, Sonnet 5.5, Fable 5.1 or Mythos 5.1: the Fable 5.1 and Mythos 5.1 migration guide says the check applies in the Message Batches API, and for Opus 5.5 and Sonnet 5.5 the docs do not say (see 4.3). [4.5]
7. Poll until `processing_status` is `"ended"` before reading results (the values are `in_progress`, `canceling` and `ended`). Results arrive as a JSONL stream, not an array, and stay available for 29 days after the batch is created (as of 2026-10-14). [4.5]
8. Respect batch limits: at most 100,000 requests or 256 MB per batch (as of 2026-10-14). `stream: true`, `speed` (fast mode) and `max_tokens: 0` are not allowed in a batch request. [4.5]

**Anti-patterns to catch in review**
- "Move everything to batch for the 50% saving".
- A blocking CI gate that waits on a batch, or a "batch with timeout fallback to synchronous".
- SLA maths that assumes batches finish quickly.
- Missing or non-unique `custom_id`, or results matched by position or order.
- A failure handler that checks only `errored` and ignores `expired` or `canceled`.
- A handler that treats a batch as all-or-nothing on expiry, discarding requests that succeeded.
- A full-batch resubmission.
- No sample-set dry run before a large batch.
- Batch items that define client tools and expect a completed loop.

**Exam answer vs current practice**
- *Tools in batches.* (Guide/exam answer, keyed: "no multi-turn tool calling" in a batch request; current, checked 2026-10-14: batches accept tool use, multi-turn conversation histories and all server tools, now including advisor.) Server tools (web search, web fetch, code execution, MCP connectors, advisor, tool search) run their server-side loop inside a batch item; the docs say the batch loop "runs more iterations per turn" before it returns `stop_reason: "pause_turn"`. Client tools still stop at `tool_use`. For tools your own code runs, both give the same answer. [4.5]
- *Retry code.* The guide's retry example raises `max_tokens` to 8192 "for oversized docs". `max_tokens` is "the maximum number of tokens to generate", so raising it helps truncated *output* (for example an incomplete `tool_use` block), not oversized *input*; chunking deals with the input. Read that comment as wrong for oversized input. [4.5]

## 4.6 Multi-instance and multi-pass review

**Rules**
1. Never rely on same-session self-review. Review with an independent instance (a new conversation with no shared history) that sees only the output. [4.6][QR]
2. Do not use "review carefully" instructions or extended thinking in the generating session as a substitute for independent review. [4.6]
3. Split large reviews: pass 1 reviews each file or unit on its own; pass 2 is a separate integration pass over all the pass-1 findings, looking for data-flow problems, API contract breaks and contradictory findings. [4.6]
4. Do not treat a larger context window or a higher-tier model as the fix for attention dilution. The problem is attention, not capacity. [4.6]
5. Route by confidence only after calibration: high-confidence findings go to developers and low-confidence findings to human review. Set the thresholds against labelled validation sets. Never route automatically on raw self-reported confidence. [4.6]
6. Production shape: generate, then per-unit independent review, then integration review, then confidence routing, then a continuing calibration loop. Accept the higher cost where missed issues have downstream consequences. [4.6]

**Anti-patterns to catch in review**
- A message array that holds the generated output as an assistant turn followed by "now review your code".
- One prompt reviewing a 10+ file change.
- Inconsistent depth across files, or the same pattern flagged in one file and passed in another.
- "Use a bigger model or context" as the remedy.
- A hard-coded threshold such as `confidence > 0.8 → auto-report` with no calibration data behind it.
- Majority vote across repeated full-PR runs offered as the fix. It is a distractor in the practice question.

**Exam answer vs current practice**
- None stated. Ambiguity: the module calibrates against "labelled validation sets", but its exercise step 5 calibrates by comparing against a fresh Claude instance's assessment. Only labelled ground truth is true calibration. [4.6]

---

## Decision rules

| Situation | Choose | Over | Why |
|---|---|---|---|
| Too many false positives in review | Explicit categories (report/skip) with code examples | "Be conservative" or a confidence filter | Vague terms give no boundary; confidence is poorly calibrated [4.1] |
| One category noisy, trust falling | Disable that category while reworking it | Leaving it on, or a second verification pass | Noise in one category destroys trust in all [4.1] |
| Severity inconsistent | A code example for each level | Prose definitions | Removes interpretation [4.1] |
| Format inconsistent despite detailed instructions | 3 to 5 few-shot examples with reasoning, in `<example>` tags (guide/exam answer: 2 to 4) | More instructions or a temperature change | Examples fix consistency; on current models a `temperature` other than 1.0 returns a 400 error anyway [4.2] |
| Fields empty when the data is in narrative text | Few-shot examples covering narrative extraction | Pre-converting to tables, a bigger context, retrying empty fields | Teaches structural variety [4.2] |
| Wrong tool selected | Better tool descriptions first, then few-shot examples | Few-shot examples alone | [4.2] |
| Guaranteed structure, one schema | `output_config.format` for a JSON response, or a tool with `strict: true` under `tool_choice` `auto` plus a prompt instruction to call it. Forced `tool` plus `strict: true` only on models that accept forcing (Haiku 5.5, Opus 5, Sonnet 5 and older) | Prompt-based JSON; a non-strict tool; forcing on Opus 5.5, Sonnet 5.5, Fable 5.1 or Mythos 5.1 | Only strict or structured outputs guarantee the schema; forcing guarantees only a call, and returns 400 on those four models and an error on any model with manual extended thinking. (Guide/exam answer: forced `tool_choice`) [4.3][QR] |
| Guaranteed structure, document type unknown | Several strict extraction tools under `auto` with a prompt instruction; `tool_choice` `any` plus `strict: true` only on models that accept forcing | Non-strict tools under `auto`; `any` on Opus 5.5, Sonnet 5.5, Fable 5.1 or Mythos 5.1 | `any` + strict guarantees both a call and a valid input where accepted; under `auto`, handle a text-only reply. (Guide/exam answer: `any` over `auto`, because `auto` may return text) [4.3] |
| Schema guarantee needed on Claude in Amazon Bedrock (any model) | Prompt instructions plus validation in code | `strict: true` or `output_config.format` | Neither is available on Claude in Amazon Bedrock (only the legacy Bedrock integration, Opus 4.6 and earlier, has them) [4.3] |
| Output shape or continuation previously forced by prefill | `output_config.format` or an enum tool for format; a system-prompt instruction for a preamble; a user message for a continuation | A trailing assistant prefill | Prefill returns 400 on every current model [GL] |
| Model fabricates missing values | Optional fields, or a type array allowing `null` (`["string", "null"]`), left out of the parent's `required` array | "Don't hallucinate" instruction, post-check, prompt JSON, `nullable: true` | Required fields cause fabrication; `nullable` is OpenAPI, not JSON Schema [4.3] |
| Ambiguous or unforeseen category | `unclear` and `other` + detail | A closed enum | Prevents forced classification [4.3] |
| Valid JSON, wrong values | Semantic validation and a retry loop | Trusting the schema | Schema ≠ correctness [4.3][4.4] |
| Validation failed and data is present | Retry with document + failed output + specific error | A naive retry | Targeted self-correction [4.4] |
| Validation failed and data is absent from the source | Null, or human review | Retry | A retry cannot create information [4.4] |
| Repeated failures (more than 2 retries) | Escalate | Keep retrying | [QR] |
| Blocking or user-facing workflow | Synchronous API | Batch | Batch has no latency SLA and can take up to 24 hours [4.5] |
| Overnight or bulk, latency-tolerant work | Batch API (50% saving, as of 2026-10-14) | Synchronous | Cost [4.5] |
| Step needs client tool execution mid-request | Synchronous, or split into request, local tool run, follow-up request | One batch item expected to complete the loop | A client tool ends the item at `tool_use`; server tools do run inside a batch item [4.5] |
| Some batch items failed | Resubmit `custom_id`s whose result is `errored`, `expired` or `canceled`, with a change (fix the request first for `invalid_request_error`) | The whole batch | Cost; finished requests keep their results [4.5] |
| Before a large batch | Refine on a sample of 5 to 10 | Submitting immediately | First-pass success drives cost [4.5] |
| Reviewing generated output | An independent instance | Same-session self-review | Reasoning bias [4.6] |
| Large multi-file review | Per-file passes + integration pass | A single pass, a bigger context or model | Attention dilution [4.6] |
| Routing uncertain findings | Calibrated thresholds | Raw confidence | Uncalibrated scores are unreliable [4.6] |
| Task has distinct phases | Prompt chaining with validation between steps | One big prompt | Focused steps; retry steps individually. The guide keys this to task statement 1.6 [QR] |

---
