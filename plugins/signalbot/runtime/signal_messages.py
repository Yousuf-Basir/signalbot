from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import export_conversations as signal_db


DEFAULT_OUTPUT_DIR = Path(os.environ.get("SIGNALBOT_OUTPUT_DIR", Path(os.environ["LOCALAPPDATA"]) / "SignalbotCodex"))
DEFAULT_MESSAGES_OUTPUT = DEFAULT_OUTPUT_DIR / "messages.json"


@dataclass(frozen=True)
class TimeFrame:
    label: str
    hours: float

    @property
    def cutoff(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(hours=self.hours)


def milliseconds(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def parse_message_json(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def compact_conversation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "type": row.get("type"),
        "name": row.get("name"),
        "profileName": row.get("profileName"),
        "profileFullName": row.get("profileFullName"),
        "e164": row.get("e164"),
        "serviceId": row.get("serviceId"),
        "groupId": row.get("groupId"),
        "active_at": row.get("active_at"),
    }


def display_name(conversation: dict[str, Any]) -> str:
    for key in ("name", "profileFullName", "profileName", "systemGivenName", "e164", "serviceId", "groupId", "id"):
        value = conversation.get(key)
        if value:
            return str(value)
    return "Unknown conversation"


def get_conversations(signal_dir: Path = signal_db.DEFAULT_SIGNAL_DIR) -> list[dict[str, Any]]:
    db_copy = signal_db.copy_database(signal_dir)
    try:
        key = signal_db.decrypt_signal_db_key(signal_dir)
        with signal_db.open_signal_database(db_copy, key) as conn:
            rows = signal_db.export_from_conversations(conn)
        return rows
    finally:
        shutil.rmtree(db_copy.parent, ignore_errors=True)


def fetch_messages(
    conversation_id: str,
    timeframe: TimeFrame,
    signal_dir: Path = signal_db.DEFAULT_SIGNAL_DIR,
) -> list[dict[str, Any]]:
    cutoff_ms = milliseconds(timeframe.cutoff)
    db_copy = signal_db.copy_database(signal_dir)

    try:
        key = signal_db.decrypt_signal_db_key(signal_dir)
        with signal_db.open_signal_database(db_copy, key) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    conversationId,
                    type,
                    body,
                    source,
                    sourceServiceId,
                    sourceDevice,
                    readStatus,
                    seenStatus,
                    sent_at,
                    received_at,
                    received_at_ms,
                    timestamp,
                    serverTimestamp,
                    expires_at,
                    hasAttachments,
                    hasFileAttachments,
                    hasVisualMediaAttachments,
                    isErased,
                    isViewOnce,
                    mentionsMe,
                    json
                FROM messages
                WHERE conversationId = ?
                  AND COALESCE(timestamp, sent_at, received_at_ms, received_at, 0) >= ?
                ORDER BY COALESCE(timestamp, sent_at, received_at_ms, received_at, 0) ASC
                """,
                (conversation_id, cutoff_ms),
            ).fetchall()

        messages = []
        for row in rows:
            message = dict(row)
            message["json"] = parse_message_json(message.get("json"))
            messages.append(message)
        return messages
    finally:
        shutil.rmtree(db_copy.parent, ignore_errors=True)


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def participant_name(row: dict[str, Any]) -> str:
    payload = parse_json_object(row.get("json"))
    for key in (
        "name",
        "profileFullName",
        "systemGivenName",
        "profileName",
        "e164",
        "username",
        "serviceId",
    ):
        value = row.get(key) or payload.get(key)
        if value:
            return str(value)
    return str(row.get("serviceId") or "Unknown")


def get_participant_map(
    source_service_ids: set[str],
    signal_dir: Path = signal_db.DEFAULT_SIGNAL_DIR,
) -> dict[str, str]:
    if not source_service_ids:
        return {}

    db_copy = signal_db.copy_database(signal_dir)
    try:
        key = signal_db.decrypt_signal_db_key(signal_dir)
        with signal_db.open_signal_database(db_copy, key) as conn:
            placeholders = ", ".join("?" for _ in source_service_ids)
            rows = conn.execute(
                f"""
                SELECT id, name, profileName, profileFullName, e164, serviceId, json
                FROM conversations
                WHERE serviceId IN ({placeholders})
                """,
                tuple(source_service_ids),
            ).fetchall()

        return {row["serviceId"]: participant_name(dict(row)) for row in rows if row["serviceId"]}
    finally:
        shutil.rmtree(db_copy.parent, ignore_errors=True)


def export_messages(
    conversation: dict[str, Any],
    timeframe: TimeFrame,
    messages: list[dict[str, Any]],
    output_path: Path = DEFAULT_MESSAGES_OUTPUT,
    signal_dir: Path = signal_db.DEFAULT_SIGNAL_DIR,
) -> dict[str, Any]:
    cutoff = timeframe.cutoff
    participant_ids = {message["sourceServiceId"] for message in messages if message.get("sourceServiceId")}
    participants = get_participant_map(participant_ids, signal_dir)

    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "signal_dir": str(signal_dir),
        "conversation": compact_conversation(conversation),
        "participants": participants,
        "timeframe": {
            "label": timeframe.label,
            "hours": timeframe.hours,
            "cutoff_at": cutoff.isoformat(),
        },
        "message_count": len(messages),
        "messages": messages,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)

    return data
