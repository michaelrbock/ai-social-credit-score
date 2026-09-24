---
name: publication-status
description: Show whether AI Social Credit Score leaderboard publishing is enabled.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/publication.py *)
---

Read the local publishing status:

!`${CLAUDE_PLUGIN_ROOT}/scripts/publication.py status --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"`

Show only the status, never the upload token.
