---
name: score
description: Show your personal AI Social Credit Score and local prompt counts.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/report.py *)
---

Your local score summary is:

!`"${CLAUDE_PLUGIN_ROOT}/scripts/report.py" --summary --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"`

Show the overall score, scored-prompt count, and data directory. Do not read or send
the raw prompt log. Also show a copyable local terminal command to inspect individual
prompts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/report.py" --data-dir "<data-directory>"`.
Replace `<data-directory>` with the directory from the summary and shell-quote it
safely. The user does not need to clone the repository to run this command.
The summary command only reads local files; it makes no model or network calls.
Mention `/ai-social-credit-score:explain` if the user wants to understand why
their score has its current value.
