---
name: unpublish
description: Stop uploading scores and delete your TransAIUnion leaderboard record and history.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/publication.py *)
---

The user explicitly requested to unpublish their score. Run:

!`${CLAUDE_PLUGIN_ROOT}/scripts/publication.py unpublish --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"`

Report the command result. If it failed, explain that uploads stopped locally but remote deletion is pending and the command should be retried. Do not claim the remote record was deleted until the command succeeds.
