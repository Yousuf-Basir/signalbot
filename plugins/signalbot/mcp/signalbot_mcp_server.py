from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = PLUGIN_ROOT / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from message_transcript import MessageTranscriptRenderer
from signal_messages import (
    DEFAULT_MESSAGES_OUTPUT,
    TimeFrame,
    display_name,
    export_messages,
    fetch_messages,
    get_conversations,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


OUTPUT_DIR = Path(os.environ.get("SIGNALBOT_OUTPUT_DIR", Path(os.environ["LOCALAPPDATA"]) / "SignalbotCodex"))
TRANSCRIPT_OUTPUT = OUTPUT_DIR / "messages_transcript.txt"
LOG_FILE = OUTPUT_DIR / "signalbot.log"


def log_event(event: str, **details: Any) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **details,
        "stdout_encoding": getattr(sys.stdout, "encoding", None),
        "stderr_encoding": getattr(sys.stderr, "encoding", None),
    }
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")


def json_response(result: Any, request_id: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(message: str, request_id: Any, code: int = -32000) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def tool_text(data: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False, indent=2, default=str),
            }
        ]
    }


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:80] or "signal"


def parse_hours(timeframe: str | None = None, hours: float | None = None) -> TimeFrame:
    if hours is not None:
        if hours <= 0:
            raise ValueError("hours must be greater than zero")
        return TimeFrame(f"{hours:g} hours", float(hours))

    if not timeframe:
        return TimeFrame("24 hours", 24)

    value = timeframe.strip().lower()
    if value == "yesterday":
        return TimeFrame("yesterday", 48)

    if value in {"last day", "1 day", "1day"}:
        return TimeFrame("1 day", 24)

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)", value)
    if match:
        parsed_hours = float(match.group(1))
        return TimeFrame(f"{parsed_hours:g} hours", parsed_hours)

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(d|day|days)", value)
    if match:
        parsed_days = float(match.group(1))
        return TimeFrame(f"{parsed_days:g} days", parsed_days * 24)

    raise ValueError("timeframe must look like '6h', '12 hours', '3 days', or 'yesterday'")


def conversation_summary(conversation: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": display_name(conversation),
        "id": conversation.get("id"),
        "type": conversation.get("type"),
        "groupId": conversation.get("groupId"),
        "active_at": conversation.get("active_at"),
    }


def resolve_conversation(name_or_id: str | None, conversations: list[dict[str, Any]]) -> dict[str, Any]:
    if not name_or_id:
        raise ValueError("conversation_name_or_id is required")

    wanted = normalize(name_or_id)
    for conversation in conversations:
        if conversation.get("id") == name_or_id:
            return conversation

    exact_matches = [c for c in conversations if normalize(display_name(c)) == wanted]
    if len(exact_matches) == 1:
        return exact_matches[0]

    partial_matches = [c for c in conversations if wanted and wanted in normalize(display_name(c))]
    if len(partial_matches) == 1:
        return partial_matches[0]

    if partial_matches:
        names = [conversation_summary(c) for c in partial_matches[:10]]
        raise ValueError(f"Multiple conversations matched. Use an id. Matches: {names}")

    raise ValueError(f"No Signal conversation matched: {name_or_id}")


def message_timestamp(message: dict[str, Any]) -> int:
    value = message.get("timestamp") or message.get("sent_at") or message.get("received_at_ms") or message.get("received_at") or 0
    return int(value)


def filter_yesterday(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).date()
    filtered = []
    for message in messages:
        ts = message_timestamp(message)
        if ts > 10_000_000_000:
            ts = ts // 1000
        if datetime.fromtimestamp(ts, tz=timezone.utc).date() == yesterday:
            filtered.append(message)
    return filtered


def filter_sender(messages: list[dict[str, Any]], sender: str | None, participants: dict[str, str]) -> list[dict[str, Any]]:
    if not sender:
        return messages

    wanted = normalize(sender)
    result = []
    for message in messages:
        if message.get("type") == "outgoing":
            speaker = "you"
        else:
            speaker = participants.get(message.get("sourceServiceId") or "", "") or message.get("source") or ""

        if wanted in normalize(str(speaker)):
            result.append(message)

    return result


def filter_mentions(messages: list[dict[str, Any]], only_mentions_to_me: bool) -> list[dict[str, Any]]:
    if not only_mentions_to_me:
        return messages
    return [message for message in messages if message.get("mentionsMe")]


def trim_messages(messages: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return messages
    return messages[-limit:]


def available_senders(messages: list[dict[str, Any]], participants: dict[str, str]) -> list[str]:
    names = set()
    for message in messages:
        if message.get("type") == "outgoing":
            names.add("You")
        else:
            source_id = message.get("sourceServiceId") or ""
            names.add(participants.get(source_id) or str(message.get("source") or "Someone"))
    return sorted(name for name in names if name)


def write_query_outputs(
    conversation: dict[str, Any],
    timeframe: TimeFrame,
    messages: list[dict[str, Any]],
    preserve_output: bool,
    suffix: str,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    filtered_data = export_messages(conversation, timeframe, messages, DEFAULT_MESSAGES_OUTPUT)
    transcript = MessageTranscriptRenderer().render(filtered_data)
    TRANSCRIPT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_OUTPUT.write_text(transcript, encoding="utf-8")

    paths = {
        "messages_json": str(DEFAULT_MESSAGES_OUTPUT),
        "transcript_file": str(TRANSCRIPT_OUTPUT),
    }

    if preserve_output:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        conversation_slug = slug(display_name(conversation))
        suffix_slug = slug(suffix)
        scoped_json = OUTPUT_DIR / f"messages_{stamp}_{conversation_slug}_{suffix_slug}.json"
        scoped_transcript = OUTPUT_DIR / f"messages_{stamp}_{conversation_slug}_{suffix_slug}.txt"
        scoped_data = export_messages(conversation, timeframe, messages, scoped_json)
        scoped_transcript.write_text(MessageTranscriptRenderer().render(scoped_data), encoding="utf-8")
        paths["preserved_messages_json"] = str(scoped_json)
        paths["preserved_transcript_file"] = str(scoped_transcript)

    return filtered_data, transcript, paths


def query_conversation(conversation: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    timeframe = parse_hours(arguments.get("timeframe"), arguments.get("hours"))
    messages = fetch_messages(conversation["id"], timeframe)
    exported = export_messages(conversation, timeframe, messages, DEFAULT_MESSAGES_OUTPUT)
    participants = exported.get("participants") or {}
    raw_count = len(messages)

    if str(arguments.get("timeframe") or "").strip().lower() == "yesterday":
        messages = filter_yesterday(messages)

    after_time_count = len(messages)
    messages = filter_mentions(messages, bool(arguments.get("only_mentions_to_me")))
    after_mentions_count = len(messages)
    sender_name = arguments.get("sender_name")
    messages = filter_sender(messages, sender_name, participants)
    after_sender_count = len(messages)
    messages = trim_messages(messages, int(arguments.get("limit") or 200))

    suffix_parts = [
        str(arguments.get("timeframe") or arguments.get("hours") or "messages"),
        str(sender_name or "all"),
    ]
    if arguments.get("only_mentions_to_me"):
        suffix_parts.append("mentions")

    filtered_data, transcript, paths = write_query_outputs(
        conversation,
        timeframe,
        messages,
        bool(arguments.get("preserve_output", True)),
        "_".join(suffix_parts),
    )

    senders = available_senders(exported.get("messages") or [], participants)
    return {
        "conversation": conversation_summary(conversation),
        "timeframe": filtered_data["timeframe"],
        "participants": filtered_data.get("participants", {}),
        "available_senders": senders,
        "counts": {
            "raw": raw_count,
            "after_time_filter": after_time_count,
            "after_mentions_filter": after_mentions_count,
            "after_sender_filter": after_sender_count,
            "returned": filtered_data["message_count"],
        },
        "message_count": filtered_data["message_count"],
        **paths,
        "log_file": str(LOG_FILE),
        "transcript": transcript,
    }


def list_recent_conversations(arguments: dict[str, Any]) -> dict[str, Any]:
    limit = int(arguments.get("limit") or 10)
    conversations = get_conversations()[:limit]
    return tool_text(
        {
            "count": len(conversations),
            "conversations": [conversation_summary(c) for c in conversations],
        }
    )


def get_messages(arguments: dict[str, Any]) -> dict[str, Any]:
    conversations = get_conversations()
    conversation = resolve_conversation(arguments.get("conversation_name_or_id"), conversations)
    result = query_conversation(conversation, arguments)
    return tool_text(result)


def search_messages(arguments: dict[str, Any]) -> dict[str, Any]:
    conversations = get_conversations()
    requested = arguments.get("conversation_names_or_ids") or []
    sender_names = arguments.get("sender_names") or []
    recent_group_limit = int(arguments.get("recent_group_limit") or 10)

    selected: list[dict[str, Any]] = []
    if requested:
        selected = [resolve_conversation(name, conversations) for name in requested]
    else:
        for sender in sender_names:
            try:
                selected.append(resolve_conversation(sender, conversations))
            except ValueError:
                pass
        selected.extend([c for c in conversations if c.get("groupId")][:recent_group_limit])

    deduped = []
    seen_ids = set()
    for conversation in selected:
        if conversation.get("id") not in seen_ids:
            seen_ids.add(conversation.get("id"))
            deduped.append(conversation)

    grouped = []
    total = 0
    for conversation in deduped:
        conversation_groups = []
        if sender_names:
            for sender_name in sender_names:
                query_args = {
                    **arguments,
                    "conversation_name_or_id": conversation.get("id"),
                    "sender_name": sender_name,
                    "only_mentions_to_me": False,
                    "preserve_output": False,
                }
                result = query_conversation(conversation, query_args)
                if result["message_count"]:
                    conversation_groups.append({"filter": {"sender_name": sender_name}, **result})
                    total += result["message_count"]

        if arguments.get("include_mentions_to_me"):
            query_args = {
                **arguments,
                "conversation_name_or_id": conversation.get("id"),
                "sender_name": None,
                "only_mentions_to_me": True,
                "preserve_output": False,
            }
            result = query_conversation(conversation, query_args)
            if result["message_count"]:
                conversation_groups.append({"filter": {"only_mentions_to_me": True}, **result})
                total += result["message_count"]

        if not sender_names and not arguments.get("include_mentions_to_me"):
            result = query_conversation(conversation, {**arguments, "conversation_name_or_id": conversation.get("id"), "preserve_output": False})
            if result["message_count"]:
                conversation_groups.append({"filter": {"all": True}, **result})
                total += result["message_count"]

        grouped.append(
            {
                "conversation": conversation_summary(conversation),
                "result_count": sum(group["message_count"] for group in conversation_groups),
                "groups": conversation_groups,
            }
        )

    summary = {
        "scanned_conversations": [conversation_summary(c) for c in deduped],
        "result_count": total,
        "results": grouped,
        "log_file": str(LOG_FILE),
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    search_path = OUTPUT_DIR / f"search_{stamp}.json"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    search_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary["search_results_json"] = str(search_path)
    return tool_text(summary)


def render_current_transcript(arguments: dict[str, Any]) -> dict[str, Any]:
    renderer = MessageTranscriptRenderer(timezone_name=arguments.get("timezone") or "Asia/Dhaka")
    transcript = renderer.render_file(DEFAULT_MESSAGES_OUTPUT, TRANSCRIPT_OUTPUT)
    return tool_text({"transcript_file": str(TRANSCRIPT_OUTPUT), "transcript": transcript})


TOOLS: dict[str, dict[str, Any]] = {
    "signalbot_list_recent_conversations": {
        "description": "List the most recent Signal Desktop conversations with display names and ids.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}},
        },
        "handler": list_recent_conversations,
    },
    "signalbot_get_messages": {
        "description": "Fetch Signal messages by conversation name/id and timeframe, optionally filtering by sender or messages mentioning the user.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_name_or_id": {"type": "string", "description": "Conversation name like 'Alma Dev On Fire' or exact conversation id."},
                "timeframe": {"type": "string", "description": "Examples: '6h', '12 hours', '3 days', 'yesterday'."},
                "hours": {"type": "number", "description": "Custom lookback in hours. Overrides timeframe when provided."},
                "sender_name": {"type": "string", "description": "Optional participant name filter, for example 'Shakil bhai' or 'Yann'."},
                "only_mentions_to_me": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 200, "description": "Maximum messages returned after filtering. 0 means no limit."},
                "preserve_output": {"type": "boolean", "default": True, "description": "Also write request-scoped timestamped output files."},
            },
            "required": ["conversation_name_or_id"],
        },
        "handler": get_messages,
    },
    "signalbot_search_messages": {
        "description": "Search multiple Signal conversations by people, timeframe, and mentions. Useful when the user asks what a person asked without naming one conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_names_or_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional explicit conversations to scan."},
                "sender_names": {"type": "array", "items": {"type": "string"}, "description": "Optional participant names to filter, such as Yann or Shakil."},
                "timeframe": {"type": "string", "description": "Examples: '5 days', 'yesterday', '12h'."},
                "hours": {"type": "number", "description": "Custom lookback in hours."},
                "include_mentions_to_me": {"type": "boolean", "default": False},
                "recent_group_limit": {"type": "integer", "default": 10, "description": "When conversations are not specified, scan this many recent groups plus matching direct chats."},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "handler": search_messages,
    },
    "signalbot_render_current_transcript": {
        "description": "Render the current messages.json file into a human-readable transcript.",
        "inputSchema": {
            "type": "object",
            "properties": {"timezone": {"type": "string", "default": "Asia/Dhaka"}},
        },
        "handler": render_current_transcript,
    },
}


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    try:
        if method == "initialize":
            return json_response(
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "signalbot", "version": "0.1.1"},
                },
                request_id,
            )

        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            return json_response(
                {
                    "tools": [
                        {
                            "name": name,
                            "description": spec["description"],
                            "inputSchema": spec["inputSchema"],
                        }
                        for name, spec in TOOLS.items()
                    ]
                },
                request_id,
            )

        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOLS:
                return error_response(f"Unknown tool: {name}", request_id, -32601)
            handler: Callable[[dict[str, Any]], dict[str, Any]] = TOOLS[name]["handler"]
            log_event("tool_call_start", tool=name, arguments={k: v for k, v in arguments.items() if k not in {"messages", "transcript"}})
            result = handler(arguments)
            log_event("tool_call_success", tool=name)
            return json_response(result, request_id)

        return error_response(f"Unsupported method: {method}", request_id, -32601)
    except Exception as exc:
        log_event("tool_call_error", error=str(exc), traceback=traceback.format_exc())
        return error_response(str(exc), request_id)


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
