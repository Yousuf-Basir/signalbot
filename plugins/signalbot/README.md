# Signalbot Codex Plugin

Signalbot lets Codex read your local Signal Desktop conversations through a local MCP server, then summarize, filter, or draft replies using the message context.

The plugin reads Signal Desktop's local encrypted database as your Windows user, copies it to a temp file, opens the copy read-only, and writes exported results to a user-local output folder.

By default on Windows, outputs are written under:

```text
%LOCALAPPDATA%\SignalbotCodex
```

The main output files are:

- `messages.json`
- `messages_transcript.txt`
- `signalbot.log`

The latest `messages.json` and `messages_transcript.txt` files are overwritten each time messages are fetched.
Single-conversation fetches also write timestamped request-scoped files by default, and multi-conversation searches write timestamped `search_*.json` files.

## What It Provides

MCP tools:

- `signalbot_list_recent_conversations`
- `signalbot_get_messages`
- `signalbot_search_messages`
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
- `preserve_output`: when true, also writes timestamped request-scoped output files

The tool returns:

- conversation metadata
- timeframe metadata
- participant name map
- available sender names for the scanned conversation/timeframe
- message count
- path to `messages.json`
- path to `messages_transcript.txt`
- preserved request-scoped output paths when enabled
- human-readable transcript text

`signalbot_search_messages` accepts:

- `conversation_names_or_ids`: optional list of conversations to scan
- `sender_names`: optional list of participant names, such as `Yann` or `Shakil`
- `timeframe`: examples include `5 days`, `yesterday`, `12h`
- `include_mentions_to_me`: include messages where Signal marks the user as mentioned
- `recent_group_limit`: when no conversation is supplied, scan matching direct chats plus recent groups

Use this tool for prompts like "what did Yann and Shakil ask me in the last 5 days?" where relevant messages may be spread across direct chats and groups.

## Install From GitHub Marketplace

Public repository:

```text
https://github.com/Yousuf-Basir/signalbot
```

Git clone URL:

```text
https://github.com/Yousuf-Basir/signalbot.git
```

In Codex, open **Add plugin marketplace** and use:

```text
Source:
Yousuf-Basir/signalbot

Git ref:
main

Sparse paths:
.agents/plugins
plugins/signalbot
```

This lets Codex load the marketplace directly from GitHub. Users do not need to clone the repository manually.

The GitHub marketplace entry points to:

```text
plugins/signalbot
```

The plugin is self-contained: its MCP server, runtime code, skill, and Python requirements all live inside the plugin folder.

## Requirements

Signalbot currently targets Windows Signal Desktop because it uses the current Windows user session to decrypt Signal Desktop's local database.

Users need:

- Signal Desktop installed and linked
- Python available as `python` on PATH
- internet access the first time the MCP server starts, so the plugin can create its local virtual environment and install dependencies

On first MCP startup, the plugin runs:

```powershell
python ./mcp/bootstrap.py
```

That bootstrap creates a plugin-local `.venv` and installs `plugins/signalbot/requirements.txt`.

The plugin expects Signal Desktop data to exist on the same Windows user account at:

```text
%APPDATA%\Signal
```

## Install / Enable Locally

If you clone the repository manually, this plugin lives at:

```text
<repo-root>\plugins\signalbot
```

The repo-local marketplace file is:

```text
<repo-root>\.agents\plugins\marketplace.json
```

In Codex, add/install the `signalbot` plugin from that local marketplace. After enabling it, ask Codex natural-language Signal questions like the examples above.

If Codex asks for the marketplace file path, use:

```text
<repo-root>\.agents\plugins\marketplace.json
```

If Codex asks for the plugin folder path directly, use:

```text
<repo-root>\plugins\signalbot
```

## Privacy Notes

Signalbot runs locally. It does not call Signal servers. It uses the same Windows user context that Signal Desktop uses to decrypt the local SQLCipher database.

Only use it for your own Signal Desktop account and conversations you are allowed to access.
