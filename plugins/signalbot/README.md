# Signalbot Codex Plugin

Signalbot lets Codex read your local Signal Desktop conversations through a local MCP server, then summarize, filter, or draft replies using the message context.

The plugin uses the Python app in `D:\personal\signalbot`. It reads Signal Desktop's local encrypted database as your Windows user, copies it to a temp file, opens the copy read-only, and writes exported results to:

- `D:\personal\signalbot\messages.json`
- `D:\personal\signalbot\messages_transcript.txt`

Both files are overwritten each time messages are fetched.

## What It Provides

MCP tools:

- `signalbot_list_recent_conversations`
- `signalbot_get_messages`
- `signalbot_render_current_transcript`

Codex skill:

- `signalbot`: tells Codex when and how to use these tools for Signal message tasks.

## Example Prompts

```text
Get last 3 days messages from Alma Dev On Fire group and tell me which messages mention me.
```

```text
Get yesterday's messages that Shakil bhai sent in Alma Dev On Fire and summarize them.
```

```text
Using this project folder and the Alma Dev On Fire Signal context, prepare a reply about what Yann wanted to know from me.
```

```text
List my recent Signal conversations.
```

## Tool Behavior

`signalbot_get_messages` accepts:

- `conversation_name_or_id`: group/person name or exact Signal conversation id
- `timeframe`: examples include `6h`, `12 hours`, `3 days`, `yesterday`
- `hours`: custom numeric lookback in hours
- `sender_name`: optional participant filter, such as `Yann` or `Shakil bhai`
- `only_mentions_to_me`: optional boolean
- `limit`: maximum messages returned after filtering

The tool returns:

- conversation metadata
- timeframe metadata
- participant name map
- message count
- path to `messages.json`
- path to `messages_transcript.txt`
- human-readable transcript text

## Install From GitHub

Private repository:

```text
https://github.com/Yousuf-Basir/signalbot
```

Git clone URL:

```text
https://github.com/Yousuf-Basir/signalbot.git
```

Use this URL when Codex asks for a GitHub plugin/repository source.

After cloning, install the Python dependencies from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The plugin expects Signal Desktop data to exist on the same Windows user account at:

```text
%APPDATA%\Signal
```

## Install / Enable Locally

This plugin lives at:

```text
D:\personal\signalbot\plugins\signalbot
```

The repo-local marketplace file is:

```text
D:\personal\signalbot\.agents\plugins\marketplace.json
```

In Codex, add/install the `signalbot` plugin from that local marketplace. After enabling it, ask Codex natural-language Signal questions like the examples above.

If Codex asks for the marketplace file path, use:

```text
D:\personal\signalbot\.agents\plugins\marketplace.json
```

If Codex asks for the plugin folder path directly, use:

```text
D:\personal\signalbot\plugins\signalbot
```

## Privacy Notes

Signalbot runs locally. It does not call Signal servers. It uses the same Windows user context that Signal Desktop uses to decrypt the local SQLCipher database.

Only use it for your own Signal Desktop account and conversations you are allowed to access.
