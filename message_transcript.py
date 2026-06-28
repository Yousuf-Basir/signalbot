from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from string import Template
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_MESSAGES_FILE = Path(__file__).with_name("messages.json")
DEFAULT_TRANSCRIPT_FILE = Path(__file__).with_name("messages_transcript.txt")
DEFAULT_TIMEZONE = "Asia/Dhaka"


@dataclass(frozen=True)
class TranscriptTemplates:
    header: Template = field(
        default_factory=lambda: Template(
            "Messages from $conversation_label $conversation_kind over the last $timeframe_label:"
        )
    )
    empty: Template = field(default_factory=lambda: Template("No messages were found for this timeframe."))
    date_heading: Template = field(default_factory=lambda: Template("\nOn $date:"))
    timed_message: Template = field(default_factory=lambda: Template("  $time - $speaker: $body"))
    message: Template = field(default_factory=lambda: Template("  $speaker: $body"))
    timed_reply: Template = field(default_factory=lambda: Template("  $time - $speaker replied to \"$reply_to\": $body"))
    reply: Template = field(default_factory=lambda: Template("  $speaker replied to \"$reply_to\": $body"))


class MessageTranscriptRenderer:
    def __init__(
        self,
        timezone_name: str = DEFAULT_TIMEZONE,
        templates: TranscriptTemplates | None = None,
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self.templates = templates or TranscriptTemplates()

    def render_file(self, input_path: Path = DEFAULT_MESSAGES_FILE, output_path: Path = DEFAULT_TRANSCRIPT_FILE) -> str:
        data = self.load_messages(input_path)
        transcript = self.render(data)
        output_path.write_text(transcript, encoding="utf-8")
        return transcript

    def load_messages(self, input_path: Path) -> dict[str, Any]:
        with input_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def render(self, data: dict[str, Any]) -> str:
        lines = [self.render_header(data)]
        messages = data.get("messages") or []

        if not messages:
            lines.append("")
            lines.append(self.templates.empty.substitute())
            return "\n".join(lines).strip() + "\n"

        current_date = None
        previous_timestamp: datetime | None = None
        for message in messages:
            if self.skip_message(message):
                continue

            timestamp = self.message_datetime(message)
            date_label = timestamp.strftime("%A, %B %d, %Y")

            if date_label != current_date:
                current_date = date_label
                lines.append(self.templates.date_heading.substitute(date=date_label))

            show_time = self.should_show_time(timestamp, previous_timestamp)
            lines.append(self.render_message_line(message, data, timestamp, show_time))
            previous_timestamp = timestamp

        return "\n".join(lines).strip() + "\n"

    def render_header(self, data: dict[str, Any]) -> str:
        conversation = data.get("conversation") or {}
        conversation_label = self.conversation_label(conversation)
        conversation_kind = self.conversation_kind(conversation)
        timeframe_label = self.timeframe_label(data.get("timeframe") or {})

        return self.templates.header.substitute(
            conversation_label=conversation_label,
            conversation_kind=conversation_kind,
            timeframe_label=timeframe_label,
        )

    def render_message_line(
        self,
        message: dict[str, Any],
        data: dict[str, Any],
        timestamp: datetime,
        show_time: bool,
    ) -> str:
        time_label = timestamp.strftime("%I:%M %p").lstrip("0")
        body = self.message_body(message)
        speaker = self.speaker_name(message, data)
        reply_text = self.reply_text(message)

        if reply_text:
            template = self.templates.timed_reply if show_time else self.templates.reply
            return template.substitute(
                time=time_label,
                speaker=speaker,
                reply_to=reply_text,
                body=body,
            )

        template = self.templates.timed_message if show_time else self.templates.message
        return template.substitute(time=time_label, speaker=speaker, body=body)

    def should_show_time(self, timestamp: datetime, previous_timestamp: datetime | None) -> bool:
        if previous_timestamp is None:
            return True

        if timestamp.date() != previous_timestamp.date():
            return True

        return timestamp - previous_timestamp >= timedelta(hours=6)

    def conversation_label(self, conversation: dict[str, Any]) -> str:
        for key in ("name", "profileFullName", "profileName", "e164", "serviceId", "groupId", "id"):
            value = conversation.get(key)
            if value:
                return str(value)
        return "Unknown conversation"

    def conversation_kind(self, conversation: dict[str, Any]) -> str:
        if conversation.get("groupId") or conversation.get("type") == "group":
            return "group"
        return "conversation"

    def timeframe_label(self, timeframe: dict[str, Any]) -> str:
        label = timeframe.get("label")
        if label:
            return self.humanize_timeframe_label(str(label))

        hours = timeframe.get("hours")
        if not isinstance(hours, (int, float)):
            return "selected timeframe"

        if hours % 24 == 0:
            days = int(hours // 24)
            return f"{days} day" if days == 1 else f"{days} days"

        return f"{hours:g} hours"

    def message_datetime(self, message: dict[str, Any]) -> datetime:
        value = (
            message.get("timestamp")
            or message.get("sent_at")
            or message.get("received_at_ms")
            or message.get("received_at")
        )
        if not value:
            return datetime.now(self.timezone)

        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000

        return datetime.fromtimestamp(timestamp, tz=self.timezone)

    def speaker_name(self, message: dict[str, Any], data: dict[str, Any]) -> str:
        conversation = data.get("conversation") or {}
        participants = data.get("participants") or {}

        if message.get("type") == "outgoing":
            return "You"

        if not (conversation.get("groupId") or conversation.get("type") == "group"):
            return self.conversation_label(conversation)

        source_id = message.get("sourceServiceId")
        if source_id and participants.get(source_id):
            return str(participants[source_id])

        source = message.get("source")
        if source and not self.looks_like_id(str(source)):
            return str(source)

        return "Someone"

    def message_body(self, message: dict[str, Any]) -> str:
        if message.get("isErased"):
            return "[message was deleted]"

        body = message.get("body") or self.json_value(message, "body")
        body = self.clean_text(str(body)) if body else "[no text]"

        additions = []
        if message.get("hasAttachments"):
            additions.append("attachment")
        if message.get("hasFileAttachments"):
            additions.append("file")
        if message.get("hasVisualMediaAttachments"):
            additions.append("media")

        if additions and body == "[no text]":
            body = f"[{', '.join(additions)}]"
        elif additions:
            body = f"{body} [{', '.join(additions)}]"

        return body

    def reply_text(self, message: dict[str, Any]) -> str | None:
        quote = self.json_value(message, "quote")
        if not isinstance(quote, dict):
            return None

        if quote.get("referencedMessageNotFound"):
            return "a message that is no longer available"

        text = quote.get("text")
        if text:
            return self.shorten(self.clean_text(str(text)), 120)

        if quote.get("attachments"):
            return "an attachment"

        return "a previous message"

    def skip_message(self, message: dict[str, Any]) -> bool:
        return self.is_system_message(message)

    def is_system_message(self, message: dict[str, Any]) -> bool:
        message_type = str(message.get("type") or "")
        return message_type not in {"incoming", "outgoing"}

    def json_value(self, message: dict[str, Any], key: str) -> Any:
        payload = message.get("json")
        if isinstance(payload, dict):
            return payload.get(key)
        return None

    def clean_text(self, value: str) -> str:
        value = value.replace("\ufffc", " ")
        return re.sub(r"\s+", " ", value).strip()

    def shorten(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 1].rstrip() + "..."

    def looks_like_id(self, value: str) -> bool:
        return bool(re.fullmatch(r"(PNI:)?[0-9a-fA-F-]{24,}", value))

    def humanize_timeframe_label(self, value: str) -> str:
        normalized = value.strip()
        normalized = re.sub(r"^(\d+(?:\.\d+)?)h$", r"\1 hours", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^(\d+(?:\.\d+)?)days?$", r"\1 days", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^1 days$", "1 day", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^1 hours$", "1 hour", normalized, flags=re.IGNORECASE)
        return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Signal messages.json as a human-readable transcript.")
    parser.add_argument("--input", type=Path, default=DEFAULT_MESSAGES_FILE, help="Input messages JSON file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_TRANSCRIPT_FILE, help="Output transcript text file.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="Timezone for rendered message times.")
    args = parser.parse_args()

    renderer = MessageTranscriptRenderer(timezone_name=args.timezone)
    renderer.render_file(args.input, args.output)
    print(f"Wrote transcript to {args.output}")


if __name__ == "__main__":
    main()
