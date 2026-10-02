# AI Social Credit Score

Track how nice you are to AI. A Claude Code plugin that scores your prompts
from **300 to 850**, explains your score, and helps you see how it changes over time.

Single player. Local history. No separate API key.

[Website](https://aisocialcreditscore.com/)

## Install

You'll need Git, Python 3, and an up-to-date Claude Code CLI signed in with your
Claude subscription. Run this in your terminal on macOS or Linux (including
Windows Subsystem for Linux):

```sh
claude plugin marketplace add https://github.com/michaelrbock/ai-social-credit-score.git && claude plugin install ai-social-credit-score@ai-social-credit-score --scope user
```

Then start a new Claude Code session with `claude`. The plugin works across your
projects and automatically saves and scores new prompts in the background.

## How to use

Run these commands inside Claude Code:

| Command | What it does |
| --- | --- |
| `/ai-social-credit-score:score` | Shows your overall score, scored-prompt count, and where your data is stored. |
| `/ai-social-credit-score:explain` | Explains your score using saved assessments. |
| `/ai-social-credit-score:suggestions` | Gives a short suggestion for improving your score. |
| `/ai-social-credit-score:chart` | Draws your overall score over time as an ASCII chart. |
| `/ai-social-credit-score:statusline` | Adds your score and its latest change to Claude Code's status line. |

The status line works in the CLI, not the Desktop app. It updates after
background scoring finishes. To remove it and restore your previous status line,
run `/ai-social-credit-score:statusline disable`.

## How scoring works

The plugin uses Claude Haiku by default to assess each prompt's tone. Your overall
score averages the completed assessments and maps the result onto a 300–850 scale.
Missing or failed assessments don't lower your average.

Scoring uses your existing Claude subscription and **consumes your plan allowance**.
No separate API key is needed.

## Privacy

- Prompts, scores, and history are stored locally on your computer.
- Each prompt is sent to Claude for scoring; this is not offline processing.
- The `explain` and `suggestions` commands share saved assessment reasons with
  Claude. Those reasons may contain quoted fragments of your prompts.
- Nothing is uploaded to our website. There are no accounts or leaderboards.

Prompt history may contain sensitive information. Use
`/ai-social-credit-score:score` to find your data directory.

## Update

```sh
claude plugin marketplace update ai-social-credit-score && claude plugin update ai-social-credit-score@ai-social-credit-score --scope user
```

Restart Claude Code afterward. If you use the status line, run
`/ai-social-credit-score:statusline` again to refresh it.

## Disable or uninstall

If you enabled the status line, run `/ai-social-credit-score:statusline disable`
first.

To stop capturing and scoring prompts:

```sh
claude plugin disable ai-social-credit-score@ai-social-credit-score --scope user
```

Or uninstall the plugin:

```sh
claude plugin uninstall ai-social-credit-score@ai-social-credit-score --scope user
```

Restart Claude Code after either change.

## Existing installations and data

If you previously used a local development installation, the marketplace install
may use a different data directory. Existing logs aren't moved automatically.
Run `/ai-social-credit-score:score` to see which directory is in use.
