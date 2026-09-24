---
name: reroll-username
description: Generate a new AI Social Credit Score username while keeping the same private identity.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/identity.py *)
---

The user explicitly requested a new username. Their new username is:

!`${CLAUDE_PLUGIN_ROOT}/scripts/identity.py reroll --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"`

Show only the new username to the user. Do not show the private installation ID.
