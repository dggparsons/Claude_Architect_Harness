# Domain 2: Tool Design & MCP Integration – engineering standard

**Exam weight:** 18% (stated on the guide's exam-overview page; not stated on the Domain 2 pages themselves).
**Modules:** 2.1 Tool Interface Design · 2.2 Structured Error Responses · 2.3 Tool Distribution & Tool Choice · 2.4 MCP Server Integration · 2.5 Built-in Tools.
**Sources (claudecertificationguide.com):** the five Domain 2 module pages (tagged [2.1] to [2.5]), the Domain 2 quick reference [QR], the Domain 2 glossary [GL] and the Domain 2 exercises page.
**Status of claims:** Technical claims checked against Anthropic's docs and the MCP spec on 2026-10-14; corrections applied inline. Evidence: `references/verification.md`.

---

## 2.1 Tool interface design

**Rules**
1. Treat the tool description as the most important part of a tool definition. Anthropic calls detailed descriptions "by far the most important factor in tool performance" and asks for at least 3–4 sentences each. Write it with care, not as metadata. Names still matter: when tools span several services, Anthropic also recommends meaningful namespacing in tool names (service-prefixed, for example `github_list_prs`). (Guide/exam answer: descriptions are the "PRIMARY" selection mechanism and matter more than names; current: Anthropic does not rank descriptions against names.) [2.1][QR]
2. Give every tool description five elements: what it does; inputs it expects (types, formats, constraints, required versus optional); example queries it handles; edge cases and limits (what it does NOT do); and explicit boundaries naming the sibling tool to use instead. The QR adds "what it returns (shape of the response)". [2.1][QR]
3. When two tools in a small toolkit are misrouted, fix the descriptions first. Choose that over few-shot examples (token cost, treats the symptom), a routing classifier (over-engineered, bypasses the model's language understanding) or consolidation (valid later, but more effort). [2.1]
4. Count the tools before choosing the remedy. Descriptions fix lookalike tools in a workable set; in a large set the cause is decision complexity, and rewriting descriptions does not help (see 2.3). (Guide convention, not a documented limit: "roughly 4–5 tools per agent" is the guide's threshold. Anthropic documents that selection "degrades once you exceed 30–50 available tools" and recommends tool search from 10 or more tools.) [2.1][QR]
5. Split a generic, broad tool (for example `analyze_document`) into purpose-specific tools, each with a defined input/output contract. [2.1]
6. When two tool names are confusingly similar, rename at the interface (for example `analyze_content` to `extract_web_results`) and give it a specific description; the implementation need not change. [2.1]
7. After changing tool descriptions, re-read the system prompt for keyword-triggered instructions ("always check customer details…") that create unintended tool associations, and rewrite them. [2.1]
8. Name parameters descriptively (`customer_email`, not `email`), mark a parameter `required` only when it truly is, and use `enum` for constrained choices. [QR][GL]
9. Measure selection accuracy on a fixed query set before and after a description change (the exercise uses 10 queries and expects 9–10/10 after). [2.1 exercise]

**Anti-patterns to catch in review**
- One-line descriptions such as "Retrieves customer information" or "Searches code".
- Two tools whose descriptions accept the same identifiers with no "Do NOT use for … use X" line.
- A catch-all tool (`analyze_*`, `process_*`, `handle_*`) whose description ends "returns results".
- Few-shot tool-selection examples added to a system prompt to paper over vague descriptions.
- A keyword router placed in front of the model as the first fix for misrouting.
- System prompt lines that bind a common keyword to one tool.
- Free-text string parameters where the valid values are a fixed set; every parameter marked required.

**Exam answer vs current practice**
- The source gives no "current state" note for 2.1. The 4–5 tools figure is the guide's own heuristic; no Anthropic page gives it. Anthropic's documented figures: selection degrades past 30–50 available tools, and standard tool calling without tool search suits fewer than 10 tools. Answer 4–5 on the exam; use Anthropic's figures in real work. [2.1][QR]
- "Descriptions matter more than names" is the exam answer. Anthropic's docs make descriptions the most important factor but do not rank them against names, and recommend namespaced names. [2.1][QR]
- Ambiguity: the glossary says "know the concept of tool filtering or routing to narrow down available tools", while the same entry and 2.1 say a routing layer is keyed wrong as the fix. Read it as: application-level pre-filtering exists as a concept, but it is not the exam's first fix. [GL]

---

## 2.2 Structured error responses

**Rules**
1. Separate the two MCP error layers (MCP spec revision 2026-07-28; this split has applied since revision 2025-11-25). Protocol errors are JSON-RPC `error` objects handled by the host: an unknown tool (`-32602`), a request that fails the `CallToolRequest` schema itself, or a server error. Tool execution errors are normal results with `isError: true`, which the model can see and act on: API failures, input validation errors (wrong format, value out of range) and business logic errors. Return argument and input-validation failures as execution errors so the model can self-correct; the spec says errors that originate from the tool "SHOULD be reported inside the result object, with isError set to true". (Guide/exam answer: protocol errors cover a request where "the arguments fail the input schema", fixed in the schema or client; current: argument validation failures are tool execution errors.) [2.2]
2. Set `isError: true` on every execution failure so the model does not read error text as a successful result. [2.2]
3. Never return a generic error ("Operation failed"). The spec asks for "actionable feedback that language models can use to self-correct". The guide's convention is to return `errorCategory`, `isRetryable` and an actionable `description` in `structuredContent`; these field names are not part of the MCP spec. [2.2]
4. Classify every failure as `transient`, `validation`, `business` or `permission`; only `transient` is retryable. (Guide convention, not MCP spec or Anthropic docs: this four-category taxonomy is the guide's application-level design.) [2.2][QR]
5. Recovery by category: transient – resend the same call after a delay; validation – correct the input and send a new call; business – do not retry, take an alternative path or escalate; permission – escalate or retry as a principal with the right access. [2.2]
6. Read `isRetryable: false` as "do not resend this exact call", never as "abandon the task". [2.2]
7. Return a successful query that finds nothing as a valid empty result (`isError: false`, plus the guide's convention field `resultCount: 0`, and text saying the query ran). Never shape it like a failure; "not found" is not an error category. [2.2][QR]
8. Never silently swallow an access failure, and never return an empty result as success when the tool could not reach the source. [2.2][QR]
9. In multi-agent systems, retry transient failures locally in the subagent; propagate only what cannot be resolved locally; include partial results and what was attempted ("3 of 5 sources succeeded…"). [2.2]
10. Branch agent recovery code on `errorCategory` (the exercise retries transient up to 3 times with backoff, reformats on validation, escalates business, requests credentials on permission). [2.2 exercise]

**Anti-patterns to catch in review**
- Error paths that return plain text without `isError: true`.
- Argument or input-validation failures returned as JSON-RPC protocol errors, which the client may not pass to the model, so it cannot self-correct.
- Tool-result schema checks that reject `resultType` or `_meta`.
- `catch` blocks that return `[]`, `null` or "no results" on a timeout or auth failure.
- Retry loops that retry on empty results, or retry every error regardless of category.
- `isRetryable: true` on validation, business or permission errors.
- Error descriptions that say what failed but not what to do next.
- A subagent that aborts the whole workflow on one failed source, or reports failure without partial results.

**Exam answer vs current practice**
- The category fields are an application convention, not part of the MCP envelope. (Guide/exam answer: `CallToolResult` defines only `content`, `structuredContent` and `isError`; current, revision 2026-07-28: it has `content` (required), `structuredContent` (optional, any JSON value), `isError` (optional, assumed false if not set), `resultType` (required from servers on this revision; `"complete"` for a final result, `"input_required"` when the server needs input; clients treat it as `"complete"` when an older server omits it) and `_meta` (optional).) Know the category names for the exam; do not expect them in the spec. [2.2][QR]
- Spec revision: the guide links the 2025-06-18 tools page. The current revision is 2026-07-28 (`modelcontextprotocol.io/specification/2026-07-28/server/tools`, or `/specification/latest/`), and the error split changed between them: input validation errors moved from protocol errors to tool execution errors in revision 2025-11-25 and remain so in 2026-07-28 (rule 1). [2.2]
- Exam guide v1.0 states `retriable: false` for business errors (note the spelling) and assigns no value for validation. The site fills validation as `false` from gRPC/AWS convention. Exam focus is the category and its recovery. [2.2]
- Two different flags appear: MCP results use `isError`; the glossary describes the Claude API `tool_result` with `is_error: true`. Both are correct for their layer; do not mix them. [2.2][GL]

---

## 2.3 Tool distribution and tool_choice

**Rules**
1. Give each agent only the tools its role needs, and keep the set small. (Guide convention, not a documented limit: "ideally 4–5" per agent, with 18 tools cited as degraded. Anthropic documents degradation "once you exceed 30–50 available tools" and recommends tool search from 10 or more tools.) [2.3]
2. Keep tools out of agents whose role does not need them (no web search on a synthesis agent), because out-of-role tools get misused and duplicate work. [2.3]
3. When tools are different jobs, split by role into focused agents. When tools are variations of one job with a shared shape, consolidate into one parameterised tool with an `enum` operation selector (22 tools became 4 in the example). Anthropic gives the same advice: group related operations "into a single tool with an `action` parameter". [2.3][QR]
4. Never treat a second MCP server as a fix for tool overload: the host runs one MCP client per server (each client talks to exactly one server) and gives the model the tools of all servers together. [2.3]
5. Replace generic tools with constrained ones (`load_document` that validates document URLs instead of `fetch_url`). This is least privilege in the interface. [2.3]
6. For frequent simple cross-role needs, give the agent a scoped cross-role tool (a `verify_fact` limited to simple single-source lookups) and route only complex cases through the coordinator. [2.3]
7. Know the four `tool_choice` modes, always written as objects, never bare strings: `{"type": "auto"}` (default when tools are provided), `{"type": "any"}` (must use one of the tools, chooses which), `{"type": "tool", "name": …}` (forces one tool) and `{"type": "none"}` (no tools; default when no tools are provided). Use `auto` for agentic loops. [2.3][QR]
8. Choose the mode in code per model; never hard-code forced `tool_choice`. On Claude Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, `any` and `tool` return a 400 error: use `auto` with `strict: true` for schema-valid tool inputs, or structured outputs for a reply in a fixed JSON shape. With manual extended thinking (`thinking: {type: "enabled"}`), on any model, `any` and `tool` are not supported and result in an error: use `auto` or `none`. Forcing a tool also skips thinking on every model that accepts it. (Guide/exam answer: `any` when output must be a tool call but the schema varies; forced `tool` for one known schema or a mandatory first step, then back to `auto`; never `auto` when structured output is required. Current: that holds only on models that still accept forced tool use.) [2.3][QR]
9. Keep the coordinator free of domain tools; it holds the subagent-spawning tool and review tools. [2.3]

**Anti-patterns to catch in review**
- Agent definitions with more tools than the role needs (the guide's convention flags more than about five), or a single "all tools" list shared by every agent.
- A tool list split across MCP servers presented as a reduction.
- Families of near-identical tools (`pivot_table`, `calculate_percentile`, …) not consolidated.
- `fetch_url`, unrestricted shell or generic HTTP tools given to subagents with narrow jobs.
- `tool_choice` written as a bare string (`"any"`) instead of an object.
- Hard-coded `any` or forced `tool` choice, which returns 400 on Claude Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, and results in an error on any model with manual extended thinking.
- Extraction calls using plain `auto` with neither `strict: true` nor structured outputs; workflows relying on prompt wording to make a step run first.
- Every simple lookup bounced through the coordinator.

**Exam answer vs current practice**
- No "current state" note in 2.3. One naming change is recorded: the coordinator's subagent tool is "`Agent` (formerly `Task`)". Confirmed: renamed in Claude Code version 2.1.63; existing `Task(...)` references in settings and agent definitions still work as aliases. [2.3]
- `tool_choice` shape: 2.3 writes objects (`{"type": "any"}`), which is correct; the QR's string form `tool_choice: "any"` is wrong. The API form is always an object. [2.3][QR]
- `tool_choice` modes: the guide lists three; there are four (`none` is the fourth). [2.3][QR]
- Forced tool use: the guide's keyed answers (`any` or forced `tool` for extraction and mandatory first steps) are the exam answer. On current models (Claude Opus 5.5, Sonnet 5.5, Fable 5.1, Mythos 5.1) they return 400; use `auto` + `strict: true` or structured outputs in real work. [2.3][QR]

---

## 2.4 MCP server integration

**Rules**
1. Put team-wide servers in `.mcp.json` at the repository root, committed. Put personal or experimental servers in `~/.claude.json`: local scope (the default, this project only) or user scope (all your projects), never team servers. (Exam answer: "user" configuration.) [2.4]
2. Declare remote servers with `"type": "http"` and a `url`; local servers with `command` and `args` (stdio). Never leave a `url` entry without `type`. [2.4]
3. Never commit credentials. Reference them as `${VAR}`; use `${VAR:-default}` only for values with a safe fallback such as paths. For remote (`http`) servers, put credentials in `headers` (for example `"Authorization": "Bearer ${GITHUB_MCP_PAT}"`); `env` only sets environment variables for a stdio server's process and will not authenticate a remote server. [2.4]
4. Do not rely on a missing variable failing loudly. An unset variable with no default does not stop the config loading: Claude Code reports a missing-variable warning in `claude mcp list` output and passes the literal `${VAR}` text through. Worse, for a documented set of credential names (Claude Code's own such as `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`, cloud-provider ones such as `AWS_BEARER_TOKEN_BEDROCK`, and others such as `NPM_TOKEN` and `HTTPS_PROXY`), a remote server's `url` and `headers` expand them to empty with no warning, and a `:-default` fallback is ignored. Use your own variable names, and check required variables yourself. [2.4]
5. Evaluate existing (community or official) servers first for standard integrations (Jira, GitHub, Slack, Linear, Notion). Build a custom server only for team-specific workflows, embedded business logic or proprietary systems with no existing server. [2.4][QR]
6. Expose content catalogues (issue summaries, doc hierarchies, database schemas) as MCP resources so agents need fewer exploratory calls. Resources are for reading; tools are for acting. [2.4][GL]
7. Write MCP tool descriptions detailed enough to compete with built-in tools: capability, outputs, and when to prefer it over (for example) Grep. Put the key words first: by default (Claude Code v2.1.296 or later, checked 2026-10-14) Claude Code cuts server instructions and upfront-loaded tool descriptions at 4,096 characters and deferred tool descriptions at 16,384, and tool search matches only within the shorter limit; `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` replaces both. [2.4]
8. Know how Claude Code loads MCP tools. Tool search is on by default: MCP tools are deferred, only tool names and server instructions load at session start, and Claude finds the rest through `ToolSearch`. Servers connect in the background. To force upfront loading, set `alwaysLoad: true` on a server in your configuration, or `ENABLE_TOOL_SEARCH=false`. A server author can set `_meta["anthropic/alwaysLoad"]: true` on a single tool; the user's server-level setting can override it. (Exceptions to tool search: a non-first-party `ANTHROPIC_BASE_URL`, older models and Microsoft Foundry deployments hosted on Azure load tools upfront.) Every configured server still adds to the pool the model chooses from. (Guide/exam answer: all servers' tools are discovered at connection time and available together, with no activation step; current: deferred by tool search unless forced upfront.) [2.4]
9. Choose `stdio` for local tools and streamable HTTP for remote or shared servers. In streamable HTTP each message is an HTTP POST to one MCP endpoint and the reply is either a JSON object or a request-scoped SSE stream, so SSE is optional. The older standalone SSE transport is deprecated in Claude Code. (Guide: streamable HTTP is "HTTP with server-sent events".) [GL]

**Anti-patterns to catch in review**
- Literal tokens, keys or connection strings in `.mcp.json` (check `env` and `headers`).
- A remote server's credential placed in `env` instead of `headers`.
- Variables from the documented set that read as empty in a remote server's `url` or `headers` (Claude Code's own credentials such as `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`, cloud-provider credentials such as `AWS_BEARER_TOKEN_BEDROCK`, and the others the MCP docs list). A name outside that set, such as `API_KEY`, expands as written.
- A team-required server documented only as "add it to your `~/.claude.json`".
- `url` entries with no `type`; `npx` lines for services that ship an official remote server.
- A custom MCP server for a standard integration with no recorded evaluation of existing ones.
- MCP tools described in one line, so the agent falls back to Grep or Bash.
- Agents calling `list_tables` then `describe_table` repeatedly where a schema resource would do.

**Exam answer vs current practice**
- Scopes: exam guide v1.0 has two levels (project and user); the exam answer is that split. The Claude Code MCP docs (checked 2026-10-14) list three scopes, `local` (default), `project` and `user`, chosen with `-s`/`--scope`, with `~/.claude.json` holding both local and user entries. [2.4]
- Resources: the exam framing is that resources give the agent the catalogue "upfront". The MCP spec (revision 2026-07-28; the guide dates it September 2026) makes resources application-controlled: the client decides when to attach one. Claude Code surfaces them through `@server:protocol://resource/path` mentions and the `ListMcpResourcesTool` and `ReadMcpResourceTool` tools. [2.4]
- Build-vs-use: the exam says "community servers"; the guide's current-state text says GitHub and Atlassian now ship official remote servers. Only GitHub's (`https://api.githubcopilot.com/mcp/`, authenticated with a personal access token in a header) is confirmed in Anthropic's docs; the Atlassian claim, its URL and the guide's `@modelcontextprotocol/server-filesystem` npx example are unverified. [2.4]
- Tool loading: the guide's "all tools available at connection time" is superseded by tool search, on by default (rule 8). [2.4]
- Architecture: each MCP client talks to exactly one server (1:1), and one host runs many clients. The QR's "connects to one server" is right; the glossary's "one or more MCP servers" is wrong. [QR][GL]

---

## 2.5 Built-in tools

**Rules**
1. Search file contents (callers, error strings, imports) with a content search, and find files by path or name pattern (`**/*.test.tsx`) with a path search. Never use a path search to find callers. Which tool does each job depends on the platform: on Windows, Grep and Glob are in the default tool set, so use Grep for contents and Glob for paths. On macOS, Linux and WSL, Claude Code leaves Grep and Glob out of the default set, and Claude searches with `find` and `grep` through Bash (embedded `bfs` and `ugrep`); there, those are the default route. Grep and Glob come back when named in `--tools` or `--allowedTools`, when Bash is removed, or when a subagent lists them without Bash. Hooks and permission rules see the Bash searches as `Bash` calls. (Guide/exam answer: Grep for contents, Glob for paths, everywhere.) [2.5][QR]
2. Use the most specific tool; avoid Bash for jobs Read or Edit handle better, and for searches on Windows, where Grep and Glob are default. [QR]
3. Use Edit for modifications. On a non-unique match, widen `old_string` until it is unique, or set `replace_all: true` if every occurrence should change; fall back to Read + Write only when neither works. Never default to Read + Write. [2.5]
4. Build understanding incrementally: Grep for entry points (on macOS, Linux and WSL, Bash `grep`), Read to follow imports, search again for new names, Read only what each step justifies. Never read all files upfront. [2.5]
5. When tracing usage, read the defining module and any barrel file, then Grep (on macOS, Linux and WSL, Bash `grep`) for every exported or re-exported name; a single search misses consumers of renamed exports. [2.5]
6. To find callers of a deprecated function and their tests: Grep for the name, Glob for each caller's sibling test file, then Grep for wrapper names. Not Glob first. (On macOS, Linux and WSL the same order applies with Bash `grep` and `find`.) [2.5]

**Anti-patterns to catch in review**
- On Windows, `find`/`grep` pipelines in Bash where Grep and Glob are available. Do not flag Bash `find`/`grep` on macOS, Linux or WSL, where it is the default search route.
- A content search used to find files by extension.
- Whole-file rewrites for one-line changes.
- Tests or hooks that match on Edit error wording such as "old_string matches 3 locations"; the uniqueness rule is documented, that text is not.
- Sessions or agent prompts that start by reading every file in a directory.
- Refactors that searched only the original function name and missed re-exports.

**Exam answer vs current practice**
- Edit fallback: exam guide v1.0 names Read + Write ("Using Read to load full file contents followed by Write when Edit cannot find unique anchor text"); answer that on the exam. The Claude Code tools reference (checked 2026-10-14) documents the current behaviour: when `old_string` appears more than once, Claude supplies a longer string with enough context, or sets `replace_all: true`; do that in real work. [2.5][QR]
- Tool count (Guide/exam answer: Claude Code "provides six built-in tools", Read, Write, Edit, Bash, Grep and Glob; current: far more). The tools reference lists 46 rows, one marked removed, including `Agent`, `Skill`, `WebFetch`, `WebSearch`, `NotebookEdit`, `LSP`, `PowerShell`, `ToolSearch`, `ListMcpResourcesTool` and `ReadMcpResourceTool`. Treat "six" as the exam's codebase subset. Grep and Glob are default only on Windows (rule 1). [2.5][2.3]

---

## 3. Decision rules

| Situation | Choose | Over | Why |
|---|---|---|---|
| Small toolkit, two lookalike tools misrouted | Expand descriptions | Few-shot, routing classifier, consolidation | Lowest effort, fixes root cause [2.1] |
| Misselection with a large toolkit (guide example: 22 tools) | Split by role or consolidate | Rewriting descriptions | Problem is decision complexity; Anthropic documents degradation past 30–50 tools and recommends tool search from 10+ [2.3][QR] |
| Many tools that are different jobs | Role-scoped agents, few tools each (guide convention: 4–5) | One agent with all tools | Selection degrades with count [2.3] |
| Many tools that are variants of one job | One parameterised tool with `enum` | Splitting by role | Splitting moves the overload down a level [2.3] |
| Overload "fixed" by a second MCP server | Reject; split or consolidate | Server split | Host pools every server's tools for the model [2.3] |
| Generic broad tool | Purpose-specific tools | One `analyze_*` tool | Clear contracts [2.1] |
| Similar tool names | Rename at the interface | Reimplementing | Overlap is in the interface [2.1] |
| Need schema-valid tool inputs on Claude Opus 5.5, Sonnet 5.5, Fable 5.1 or Mythos 5.1 | `{"type": "auto"}` + `strict: true`; structured outputs for a fixed JSON reply | `any` or forced `tool` | `any` and `tool` return 400 there [2.3] |
| Manual extended thinking (`thinking: {type: "enabled"}`) on any model | `{"type": "auto"}` or `{"type": "none"}` | `any` or forced `tool` | `any` and `tool` are not supported there and result in an error [2.3] |
| Need some tool call, schema unknown, on a model that accepts forcing (exam answer) | `{"type": "any"}` | `auto` | Guarantees a tool call [2.3][QR] |
| One known schema / mandatory first step, on a model that accepts forcing (exam answer) | Forced `{"type": "tool", "name": …}`, chosen in code per model | `any` or prompt wording | Guarantees that specific call; skips thinking [2.3] |
| Claude must not use any tool on this turn | `{"type": "none"}` | – | Fourth mode; also the default when no tools are given [2.3] |
| General agentic loop | `auto` | `any` or forced | Model may need to answer in text [QR] |
| Frequent simple cross-role lookups | Scoped cross-role tool | Coordinator round trip | Avoids 2–3 hops / ~40% latency [2.3] |
| Agent needs documents only | Constrained `load_document` | `fetch_url` | Least privilege [2.3] |
| Query ran, found nothing | Valid empty result, accept | Error / retry | Absence is the answer [2.2] |
| Arguments fail validation (wrong format, out of range) | Tool execution error, `isError: true` | JSON-RPC protocol error | Model can see it and self-correct (spec since 2025-11-25; current revision 2026-07-28) [2.2] |
| 401 or timeout | Access failure: retry (transient) or escalate | Treating as empty | Something went wrong [2.2][QR] |
| Business rule rejected the call | Alternative path or escalate | Retry | Same result every time [2.2] |
| Subagent transient failure | Local retry, then propagate with partial results | Suppress or abort workflow | Coordinator needs context [2.2] |
| Standard integration needed | Existing community/official server | Custom build | Maintained, tested [2.4] |
| Team-wide MCP server | `.mcp.json` at project root | `~/.claude.json` | Shared via version control [2.4] |
| Personal/experimental server | `~/.claude.json` (local scope by default; user scope for cross-project) | `.mcp.json` | Not shared [2.4] |
| Credentials in shared config | `${VAR}` expansion, with your own variable names | Literal values; covered credential names (`ANTHROPIC_API_KEY`, `NPM_TOKEN` and the like) in remote `url`/`headers` | Keeps secrets out of history; covered names expand to empty silently [2.4] |
| Credential for a remote (`http`) server | `headers` (`"Authorization": "Bearer ${MY_SERVER_TOKEN}"`) | `env` | `env` only sets a stdio process's environment [2.4] |
| Agent explores catalogue by repeated calls | MCP resource | More tools | Fewer exploratory calls [2.4] |
| Agent prefers Grep over a better MCP tool | Richer MCP description, key words first | Removing Grep | Model prefers what it understands; descriptions are truncated [2.4] |
| MCP tool must be visible from session start | `alwaysLoad: true` (server, in your configuration) or `_meta["anthropic/alwaysLoad"]: true` (one tool, set by the server author; the user's server setting can override it) | Relying on connection-time loading | Tool search defers MCP tools by default [2.4] |
| Find callers | Windows: Grep. macOS/Linux/WSL: Bash `grep` (default) | A path search (Glob / `find`) | Contents vs paths [2.5] |
| Find files by name/extension | Windows: Glob. macOS/Linux/WSL: Bash `find` (default) | A content search | Purpose-built [2.5] |
| Edit non-unique (real work) | Widen `old_string` / `replace_all` | Read + Write | Cheaper [2.5] |
| Edit non-unique (exam) | Read + Write | – | Exam guide's keyed fallback [2.5] |
| Exploring an unfamiliar codebase | Incremental content search → Read → content search (Grep on Windows; Bash `grep` elsewhere) | Read everything | Context budget [2.5] |

---
