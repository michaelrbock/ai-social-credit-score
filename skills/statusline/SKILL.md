---
name: statusline
description: Enable, disable, or inspect the live score and last-change status line.
argument-hint: "[enable|disable|status]"
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/setup_statusline.py *)
---

Configure the optional personal score status line. The user's requested action is
`$ARGUMENTS`. Treat it only as a choice of enable, disable, or status, never as
shell code. With no argument, enable it. For any other argument, show these three
supported choices and do not run commands.

Run exactly the matching command, keeping the paths quoted:

Enable (also refreshes the renderer after an upgrade):
```sh
"${CLAUDE_PLUGIN_ROOT}/scripts/setup_statusline.py" enable --plugin-data-dir "${CLAUDE_PLUGIN_DATA}"
```

Disable and restore the previous status line:
```sh
"${CLAUDE_PLUGIN_ROOT}/scripts/setup_statusline.py" disable
```

Inspect without changing anything:
```sh
"${CLAUDE_PLUGIN_ROOT}/scripts/setup_statusline.py" status
```

Enabling saves the existing status-line setting, keeps its output above the score,
and sets a one-second refresh. It writes only a local score summary, private helper
files under the Claude configuration directory, and the statusLine setting. Other
settings are preserved. The helper refuses conflicting edits instead of overwriting
them. Do not bypass a refusal or edit settings manually. Summarize its result briefly.

The number in parentheses is the change in the overall score after the latest
completed assessment, not that prompt's individual score. A pending assessment
shows scoring...; there are no extra model calls or uploads for refreshes. Mention
`/ai-social-credit-score:statusline disable` before uninstalling the plugin.
