---
name: chart
description: Show an ASCII chart of your cumulative AI Social Credit Score over time.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/chart.py *)
---

The user's local score chart is:

!`"${CLAUDE_PLUGIN_ROOT}/scripts/chart.py" --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"`

Return the complete output above verbatim inside one fenced `text` code block so
the ASCII chart stays aligned. Include its labels, legend, and any empty-history
or skipped-record notes. Do not redraw it, change its values, or add commentary.
The trail is the reconstructed cumulative overall score, not individual prompt
scores. The helper reads only saved assessments and does not read raw prompts,
call a model, make network requests, or change the user's history. Do not run
additional commands or re-score anything.
