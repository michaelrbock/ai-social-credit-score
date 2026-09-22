# AI Social Credit Score

A Claude Code plugin that captures each submitted user prompt and can
asynchronously score its communication style with the user's existing Claude
Code subscription.

Capture and scoring are both local plugin operations. When scoring is enabled,
the raw prompt is sent to Claude through a locked-down `claude -p` child process;
the resulting structured score is written locally. Scoring is opt-in and disabled
by default.

## Requirements

- Claude Code installed, authenticated, and available as `claude` on `PATH`
- A Claude subscription for the default scoring backend
- Python 3

This version is tested against Claude Code 2.1.243.

## Try capture locally

From this repository:

```sh
claude plugin validate . --strict
claude --plugin-dir .
```

Submit a normal prompt. Inside Claude Code, `/hooks` should show an asynchronous
`UserPromptSubmit` command hook provided by the plugin.

Claude Code supplies installed plugins with a persistent `$CLAUDE_PLUGIN_DATA`
directory, where this plugin stores `prompts.jsonl`, `scores.jsonl`, and
`score_errors.jsonl`. During local development, you can choose a predictable
location explicitly:

```sh
AI_SOCIAL_CREDIT_SCORE_DATA_DIR="$HOME/Library/Application Support/ai-social-credit-score" \
claude --plugin-dir .
```

Then inspect the latest captured prompt:

```sh
tail -n 1 "$HOME/Library/Application Support/ai-social-credit-score/prompts.jsonl"
```

Each prompt record includes a join key:

```json
{
  "schema_version": 1,
  "prompt_id": "437a9f90-c7ef-4603-8e47-f992f16c391d",
  "captured_at": "2026-08-24T23:45:00.000000Z",
  "event": "user_prompt",
  "session_id": "example-session-id",
  "cwd": "/path/to/project",
  "prompt": "Please explain this test failure."
}
```

The hook does not copy Claude Code's transcript path, responses, tool calls,
permission mode, or source files.

## Enable subscription-backed scoring

Start a new Claude Code session with scoring explicitly enabled:

```sh
AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED=1 \
AI_SOCIAL_CREDIT_SCORE_DATA_DIR="$HOME/Library/Application Support/ai-social-credit-score" \
claude --plugin-dir .
```

No Anthropic API key is required. For each prompt, the asynchronous command hook:

1. Captures the prompt locally.
2. Runs a headless `claude -p` scorer using the existing subscription login.
3. Enforces the score shape with `--json-schema`.
4. Appends the result to `scores.jsonl` using the same `prompt_id`.

The child runs with `--safe-mode`, no tools, and no session persistence. The raw
prompt is passed over stdin rather than placed in process arguments. A separate
environment marker prevents recursion even if hook isolation changes. Direct API
and cloud-provider environment variables are removed from this child so the
default backend cannot silently switch away from subscription authentication.

Scoring is intentionally out of band and may take several seconds. Inspect the
latest completed score:

```sh
tail -n 1 "$HOME/Library/Application Support/ai-social-credit-score/scores.jsonl"
```

Example:

```json
{
  "schema_version": 1,
  "event": "prompt_score",
  "prompt_id": "437a9f90-c7ef-4603-8e47-f992f16c391d",
  "backend": "claude-code",
  "provider": "firstParty",
  "model": "claude-haiku-4-5-20251001",
  "rubric_version": "niceness-rubric-v1",
  "directedness": "directed_at_ai",
  "respect": 3,
  "warmth": 2,
  "cooperation": 3,
  "hostility": 0,
  "overall_niceness": 68,
  "confidence": 0.9,
  "rationale": "Direct and respectful, with neutral warmth."
}
```

The default pinned model is `claude-haiku-4-5-20251001`. Override it with:

```sh
AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED=1 \
AI_SOCIAL_CREDIT_SCORE_MODEL=claude-haiku-4-5-20251001 \
claude --plugin-dir .
```

This backend consumes the user's Claude plan allowance. It does not use a
separate API billing account.

## Optional direct API backend

The prior Messages API implementation remains available for development, CI, or
users who explicitly prefer separate API billing:

```sh
export ANTHROPIC_API_KEY="..."
AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED=1 \
AI_SOCIAL_CREDIT_SCORE_BACKEND=api \
claude --plugin-dir .
```

`AI_SOCIAL_CREDIT_SCORE_BACKEND` accepts:

- `claude-code` or `subscription`: use Claude Code authentication; this is the
  default.
- `api`: require `ANTHROPIC_API_KEY` and call the Messages API directly.
- `auto`: use the API only when `ANTHROPIC_API_KEY` is present; otherwise use
  Claude Code.

## Storage and diagnostics

Storage is resolved in this order:

1. `AI_SOCIAL_CREDIT_SCORE_LOG_FILE` for the exact prompt-log path.
2. `AI_SOCIAL_CREDIT_SCORE_DATA_DIR` for all plugin data.
3. Claude Code's persistent `$CLAUDE_PLUGIN_DATA` directory.
4. The platform fallback, such as
   `~/Library/Application Support/ai-social-credit-score` on macOS.

The score and error logs default next to `prompts.jsonl`. Override them with
`AI_SOCIAL_CREDIT_SCORE_SCORES_FILE` and
`AI_SOCIAL_CREDIT_SCORE_ERRORS_FILE`.

Scoring, validation, authentication, and timeout failures are written to
`score_errors.jsonl`; captured prompts are retained even when scoring fails.

Set `AI_SOCIAL_CREDIT_SCORE_DEBUG=1` for stderr diagnostics. Temporarily disable
all capture with `AI_SOCIAL_CREDIT_SCORE_DISABLED=1`.

## Privacy boundary

Prompts can contain source code, personal information, credentials, and other
sensitive text. Anyone using this plugin should understand that:

- capture and scoring are disabled or enabled independently;
- enabling scoring sends the exact prompt to Claude;
- score generation consumes the user's Claude plan allowance;
- prompts and scores are stored locally with restrictive permissions on macOS
  and Linux;
- Claude responses, transcripts, and source files are not scored or copied; and
- prompt logs should not be uploaded or analyzed without informed consent.

## Tests

The test suite uses a fake Claude executable and a mocked Messages API. It does
not consume subscription quota or make a live API request.

```sh
python3 -m unittest discover -s tests -v
```
