from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from signal_messages import (
    DEFAULT_MESSAGES_OUTPUT,
    TimeFrame,
    display_name,
    export_messages,
    fetch_messages,
    get_conversations,
)


TIMEFRAME_OPTIONS = [
    TimeFrame("6h", 6),
    TimeFrame("12h", 12),
    TimeFrame("1day", 24),
    TimeFrame("7days", 24 * 7),
    TimeFrame("15days", 24 * 15),
]

RECENT_CONVERSATION_LIMIT = 10


@dataclass(frozen=True)
class AppConfig:
    output_path: Path = DEFAULT_MESSAGES_OUTPUT


def print_conversations(conversations: list[dict], limit: int = RECENT_CONVERSATION_LIMIT) -> None:
    recent_conversations = conversations[:limit]

    print(f"\nRecent conversations (top {len(recent_conversations)}):\n")
    for index, conversation in enumerate(recent_conversations, start=1):
        identifier = conversation.get("id", "")
        print(f"{index:>2}. {display_name(conversation)}")
        print(f"    id: {identifier}")

    print("\nTip: paste any conversation id directly if it is not in this recent list.")


def choose_conversation(conversations: list[dict]) -> dict:
    recent_conversations = conversations[:RECENT_CONVERSATION_LIMIT]

    while True:
        raw_value = input("\nSelect conversation number or paste conversation id: ").strip()
        if not raw_value:
            print("Please enter a number or conversation id.")
            continue

        if raw_value.isdigit():
            index = int(raw_value)
            if 1 <= index <= len(recent_conversations):
                return recent_conversations[index - 1]
            print(f"Choose a number between 1 and {len(recent_conversations)}, or paste a conversation id.")
            continue

        for conversation in conversations:
            if conversation.get("id") == raw_value:
                return conversation

        print("No conversation matched that value.")


def print_timeframes() -> None:
    print("\nTime frames:\n")
    for index, timeframe in enumerate(TIMEFRAME_OPTIONS, start=1):
        print(f"{index}. {timeframe.label}")
    print(f"{len(TIMEFRAME_OPTIONS) + 1}. custom hours")


def choose_timeframe() -> TimeFrame:
    print_timeframes()
    custom_index = len(TIMEFRAME_OPTIONS) + 1

    while True:
        raw_value = input("\nSelect time frame: ").strip().lower()
        if not raw_value:
            print("Please select a time frame.")
            continue

        if raw_value.isdigit():
            index = int(raw_value)
            if 1 <= index <= len(TIMEFRAME_OPTIONS):
                return TIMEFRAME_OPTIONS[index - 1]
            if index == custom_index:
                return ask_custom_hours()

        for timeframe in TIMEFRAME_OPTIONS:
            if raw_value == timeframe.label.lower():
                return timeframe

        if raw_value in {"custom", "custom hours"}:
            return ask_custom_hours()

        print("Choose a listed number, label, or custom hours.")


def ask_custom_hours() -> TimeFrame:
    while True:
        raw_value = input("Enter custom hours value: ").strip()
        try:
            hours = float(raw_value)
        except ValueError:
            print("Please enter a numeric hours value.")
            continue

        if hours <= 0:
            print("Hours must be greater than zero.")
            continue

        return TimeFrame(f"{hours:g}h", hours)


def run(config: AppConfig = AppConfig()) -> None:
    conversations = get_conversations()
    if not conversations:
        print("No conversations found.")
        return

    print_conversations(conversations)
    conversation = choose_conversation(conversations)
    timeframe = choose_timeframe()

    print(f"\nFetching messages from {display_name(conversation)} for the last {timeframe.label}...")
    messages = fetch_messages(conversation["id"], timeframe)
    data = export_messages(conversation, timeframe, messages, config.output_path)

    print(f"Wrote {data['message_count']} messages to {config.output_path}")


if __name__ == "__main__":
    run()
