# AI Social Credit Score

A Claude Code plugin that captures each submitted user prompt and can
asynchronously score its communication style with the user's existing Claude
Code subscription.

## TransAIUnion leaderboard

The D1-backed website is in [`website`](website). Its leaderboard reads
published score summaries; it has no endpoint for prompt text. The plugin
calculates an overall 300–850 score locally from the mean niceness score of
successfully scored, distinct prompts, including older v1 score records.

For **new installations**, publication is enabled automatically. After a
random 1–10 newly scored prompts, the plugin uploads only its pseudonymous
username, aggregate score, scored-prompt count, latest score date, and rubric
version. It chooses a new random interval after each successful upload. The
exact prompt, rationale, project path, session ID, and per-prompt scores never
go to the website. Installations with an existing `identity.json` from before
this feature stay local-only unless the user runs
`/ai-social-credit-score:publish`.

`/ai-social-credit-score:unpublish` stops future uploads and deletes the
leaderboard record and history. Run it before uninstalling; losing the local
upload token prevents automatic deletion of the remote record. A failed delete
leaves publishing disabled and reports that remote deletion is still pending.

Capture and scoring are both local plugin operations. When scoring is enabled,
the raw prompt is sent to Claude through a locked-down `claude -p` child process;
the resulting structured score is written locally. Scoring remains opt-in and
disabled by default. The website's setup command enables scoring for one Claude
Code session; publication then follows the automatic new-install behavior above.

## Requirements

- Claude Code installed, authenticated, and available as `claude` on `PATH`
- A Claude subscription when scoring is enabled
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
directory, where this plugin stores `identity.json`, `publication.json`,
`prompts.jsonl`, `scores.jsonl`, and error logs. During local development, you can
choose a predictable location explicitly:

```sh
AI_SOCIAL_CREDIT_SCORE_DATA_DIR="$HOME/Library/Application Support/ai-social-credit-score" \
claude --plugin-dir .
```

Then inspect the latest captured prompt:

```sh
tail -n 1 "$HOME/Library/Application Support/ai-social-credit-score/prompts.jsonl"
```

## Anonymous username

On the first Claude Code session with the plugin, a `SessionStart` hook quietly
creates a fun pseudonymous username such as `CuriousCapybara274`. If that
hook does not run, the first captured prompt creates the same local identity.
No model call or personal information is used to generate it. The username and
a separate random installation ID are stored in `identity.json` beside the
prompt log. The file is private on macOS and Linux, and the identity survives
new sessions and plugin updates.
Names created in the earlier dashed format are changed to this format on first
use, while keeping the same installation ID.

Inside Claude Code, use `/ai-social-credit-score:username` to see the current
name or `/ai-social-credit-score:reroll-username` to choose another. Rerolling
keeps the installation ID stable. From this repository, the equivalent commands
are `python3 scripts/identity.py show` and `python3 scripts/identity.py reroll`.
The name is a pseudonym, not a guarantee of anonymity. The server reserves
published names and the plugin rerolls on a collision. Uninstalling the plugin
can remove its local identity and private upload token.

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
environment marker prevents recursion even if hook isolation changes. API
credentials and cloud-provider settings are removed from this child so scoring
uses the existing Claude Code subscription.

Scoring is intentionally out of band and may take several seconds. Inspect the
latest completed score:

```sh
tail -n 1 "$HOME/Library/Application Support/ai-social-credit-score/scores.jsonl"
```

Example:

```json
{
  "schema_version": 2,
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
  "credit_score": 674,
  "confidence": 0.9,
  "rationale": "Direct and respectful, with neutral warmth."
}
```

`credit_score` maps the model's 0–100 `overall_niceness` onto 300–850 with
`300 + round_half_up(5.5 × overall_niceness)`. For example, 0 → 300,
50 → 575, and 100 → 850. The underlying niceness score remains in the record
for calibration and backward compatibility. Existing `scores.jsonl` entries are
not rewritten; only newly scored prompts have `credit_score` and score schema
version 2. Only the aggregate summary described above is sent to the website.

The default pinned model is `claude-haiku-4-5-20251001`. Override it with:

```sh
AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED=1 \
AI_SOCIAL_CREDIT_SCORE_MODEL=claude-haiku-4-5-20251001 \
claude --plugin-dir .
```

Scoring consumes the user's Claude plan allowance. It does not use a separate
API billing account. If an older setup sets `AI_SOCIAL_CREDIT_SCORE_BACKEND=api`
or `auto`, remove that setting; those values are no longer supported.

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

Publishing uses a private, random token stored in `publication.json` with
restrictive permissions. The server stores only its hash. Publication failures
are written to `publish_errors.jsonl`; scoring and prompt capture continue.
Set `AI_SOCIAL_CREDIT_SCORE_PUBLISH_DISABLED=1` to temporarily suppress uploads
without deleting an existing leaderboard record. Override the upload endpoint
for local testing with `AI_SOCIAL_CREDIT_SCORE_UPLOAD_URL` (HTTPS except
localhost). `/ai-social-credit-score:publication-status` shows the local state.

Scoring, validation, authentication, and timeout failures are written to
`score_errors.jsonl`; captured prompts are retained even when scoring fails.

Set `AI_SOCIAL_CREDIT_SCORE_DEBUG=1` for stderr diagnostics. Temporarily disable
all capture with `AI_SOCIAL_CREDIT_SCORE_DISABLED=1`.

## Privacy boundary

Prompts can contain source code, personal information, credentials, and other
sensitive text. Anyone using this plugin should understand that:

- scoring is opt-in, while publishing is automatic for new installations once
  scoring produces completed scores;
- enabling scoring sends the exact prompt to Claude;
- score generation consumes the user's Claude plan allowance;
- prompts and per-prompt scores are stored locally with restrictive permissions
  on macOS and Linux;
- the website receives only the pseudonymous username, aggregate 300–850 score,
  scored-prompt count, score date, and rubric version;
- Claude responses, transcripts, and source files are not scored or copied; and
- prompt logs should not be uploaded or analyzed without informed consent.

## Tests

The test suite uses a fake Claude executable. It does not consume subscription
quota or make a live API request.

```sh
python3 -m unittest discover -s tests -v
```
