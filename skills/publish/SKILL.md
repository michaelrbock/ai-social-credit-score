---
name: publish
description: Enable score publication for an installation created before automatic publishing existed.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/publication.py *)
---

The user explicitly requested publication. Enable future uploads with:

!`${CLAUDE_PLUGIN_ROOT}/scripts/publication.py enable --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"`

Explain that only the pseudonymous username, aggregate score, scored-prompt count, score date, and rubric version will be uploaded. Prompts, rationales, project paths, and session IDs stay local.
