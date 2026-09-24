---
name: username
description: Show your AI Social Credit Score username.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/identity.py *)
---

Your locally generated username is:

!`${CLAUDE_PLUGIN_ROOT}/scripts/identity.py show --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"`

Show only the username to the user. Do not show the private installation ID.
