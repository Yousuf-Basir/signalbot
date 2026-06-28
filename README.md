# Signalbot

Signalbot is a local Python app and Codex plugin for reading your own Signal Desktop conversations from Windows, exporting filtered message context, and rendering human-readable transcripts.

It includes:

- a CLI app for selecting recent Signal conversations and timeframes
- read-only Signal Desktop database access through a copied SQLCipher database
- JSON message export
- human-readable transcript rendering
- a local Codex plugin with MCP tools and a skill

## Quick Start

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the CLI:

```powershell
.\.venv\Scripts\python.exe .\main.py
```

Render the current exported messages as a transcript:

```powershell
.\.venv\Scripts\python.exe .\message_transcript.py
```

## Codex Plugin

The plugin lives at:

```text
plugins/signalbot
```

The repo-local marketplace file lives at:

```text
.agents/plugins/marketplace.json
```

See [plugins/signalbot/README.md](plugins/signalbot/README.md) for Codex plugin usage.

To add the plugin marketplace directly from GitHub in Codex:

```text
Source: Yousuf-Basir/signalbot
Git ref: main
Sparse paths:
.agents/plugins
plugins/signalbot
```

## Privacy

Signalbot is intended for your own local Signal Desktop account. It does not modify Signal's database. Runtime exports such as `messages.json`, `messages_transcript.txt`, and `conversations.json` are ignored by git because they can contain private conversation data.
