---
name: signalbot
description: Use when the user asks Codex to read, filter, summarize, or draft replies from their local Signal Desktop conversations using the Signalbot MCP tools.
---

# Signalbot

Use this skill when the user asks about Signal Desktop messages, Signal group conversations, recent messages, mentions, sender-specific messages, or preparing replies based on Signal context.

Signalbot reads the user's local Signal Desktop profile through MCP tools. Treat the data as private. Do not reveal raw message content unless the user asks for it or it is necessary to answer the request.

## Tools

Prefer MCP tools from the `signalbot` server:

- `signalbot_list_recent_conversations`: list recent conversations with names and ids.
- `signalbot_get_messages`: fetch messages by conversation name/id and timeframe, with optional filters.
- `signalbot_search_messages`: search multiple conversations by people, timeframe, and mentions.
- `signalbot_render_current_transcript`: render the current `messages.json` into a readable transcript.

## Workflow

1. For ambiguous conversation names, call `signalbot_list_recent_conversations` and ask the user to pick the conversation if needed.
2. For requests like "last 3 days messages from Alma Dev On Fire", call `signalbot_get_messages` with:
   - `conversation_name_or_id`: the group/person name
   - `timeframe`: `3 days`
3. For mention requests, set `only_mentions_to_me` to `true`.
4. For sender requests, set `sender_name` to the person named by the user.
5. For person/timeframe requests without a named conversation, call `signalbot_search_messages` instead of guessing one chat. Include `sender_names`, `timeframe`, and `include_mentions_to_me` when relevant.
6. Use returned `available_senders` to explain zero-result sender filters and suggest the closest sender name.
7. Use the returned `transcript` or grouped `results` for summarization, reply drafting, or project-context comparison.
8. When the user adds a project folder, inspect relevant project files normally, then combine that context with the Signal transcript. Keep the reply grounded in both sources.

## Examples

User: "Get last 3 days messages from Alma Dev On Fire group and tell me what messages mention me."

Call `signalbot_get_messages`:

```json
{
  "conversation_name_or_id": "Alma Dev On Fire",
  "timeframe": "3 days",
  "only_mentions_to_me": true
}
```

User: "Get yesterday's messages that Shakil bhai sent and summarize it."

Call `signalbot_get_messages`:

```json
{
  "conversation_name_or_id": "Alma Dev On Fire",
  "timeframe": "yesterday",
  "sender_name": "Shakil bhai"
}
```

User: "Prepare a reply regarding what Yann wanted to know from me about this project."

Call `signalbot_search_messages` with:

```json
{
  "timeframe": "5 days",
  "sender_names": ["Yann"],
  "include_mentions_to_me": true
}
```

Then inspect the project folder files the user provides. Draft a concise reply that answers Yann's ask and cites project facts when useful.

## Safety

- Only use this for the current user's local Signal Desktop data.
- Do not modify Signal's database.
- Mention that the returned `messages_json` and `transcript_file` paths are overwritten on each fetch.
- Also mention preserved request-scoped output files when `preserved_messages_json` or `search_results_json` is returned.
