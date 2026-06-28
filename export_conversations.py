from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import shutil
import sqlite3
import tempfile
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import sqlcipher3


DEFAULT_SIGNAL_DIR = Path(os.environ["APPDATA"]) / "Signal"
DEFAULT_OUTPUT = Path(__file__).with_name("conversations.json")


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def dpapi_unprotect(encrypted: bytes) -> bytes:
    blob_in = DATA_BLOB(len(encrypted), ctypes.cast(ctypes.create_string_buffer(encrypted), ctypes.POINTER(ctypes.c_ubyte)))
    blob_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise ctypes.WinError()

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_chromium_master_key(signal_dir: Path) -> bytes:
    local_state = load_json(signal_dir / "Local State")
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])

    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]

    return dpapi_unprotect(encrypted_key)


def decrypt_signal_db_key(signal_dir: Path) -> bytes:
    config = load_json(signal_dir / "config.json")
    encrypted_key = bytes.fromhex(config["encryptedKey"])

    if encrypted_key.startswith(b"v10"):
        master_key = get_chromium_master_key(signal_dir)
        nonce = encrypted_key[3:15]
        ciphertext_and_tag = encrypted_key[15:]
        plaintext = AESGCM(master_key).decrypt(nonce, ciphertext_and_tag, None)
    else:
        plaintext = dpapi_unprotect(encrypted_key)

    return normalize_sqlcipher_key(plaintext)


def normalize_sqlcipher_key(raw_key: bytes) -> bytes:
    text = raw_key.decode("utf-8", errors="ignore").strip()

    if text.startswith("x'") and text.endswith("'"):
        return bytes.fromhex(text[2:-1])

    if len(text) == 64:
        try:
            return bytes.fromhex(text)
        except ValueError:
            pass

    return raw_key


def copy_database(signal_dir: Path) -> Path:
    db_path = signal_dir / "sql" / "db.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"Signal database not found: {db_path}")

    temp_dir = Path(tempfile.mkdtemp(prefix="signalbot_"))
    copied = temp_dir / "db.sqlite"
    shutil.copy2(db_path, copied)
    return copied


def open_signal_database(db_copy: Path, key: bytes) -> sqlcipher3.Connection:
    conn = sqlcipher3.connect(str(db_copy))
    conn.row_factory = sqlcipher3.Row
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    conn.execute("PRAGMA query_only = ON")

    # Forces SQLCipher to validate the key before we start introspecting schema.
    conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    return conn


def list_tables(conn: sqlcipher3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def table_columns(conn: sqlcipher3.Connection, table: str) -> list[str]:
    return [row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def first_present(columns: list[str], names: list[str]) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None


def export_from_conversations(conn: sqlcipher3.Connection) -> list[dict[str, Any]]:
    columns = table_columns(conn, "conversations")
    wanted = [
        "id",
        "e164",
        "serviceId",
        "groupId",
        "type",
        "profileName",
        "name",
        "title",
        "username",
        "active_at",
        "isArchived",
        "isPinned",
        "isMuted",
        "unreadCount",
    ]
    selected = [column for column in wanted if column in columns]

    if "id" not in selected:
        selected.insert(0, first_present(columns, ["rowid", "_id"]) or "rowid")

    order_column = first_present(columns, ["active_at", "lastMessageReceivedAt", "timestamp"])
    order_sql = f' ORDER BY "{order_column}" DESC' if order_column else ""
    sql = "SELECT " + ", ".join(f'"{column}"' for column in selected) + ' FROM "conversations"' + order_sql

    return [dict(row) for row in conn.execute(sql).fetchall()]


def export_from_messages(conn: sqlcipher3.Connection) -> list[dict[str, Any]]:
    columns = table_columns(conn, "messages")
    conversation_column = first_present(columns, ["conversationId", "conversationIdString", "sourceUuid", "source", "sent_at"])
    if not conversation_column:
        raise RuntimeError("Could not find a conversation identifier column in messages table.")

    sql = f'''
        SELECT "{conversation_column}" AS id, COUNT(*) AS message_count
        FROM "messages"
        WHERE "{conversation_column}" IS NOT NULL AND "{conversation_column}" != ''
        GROUP BY "{conversation_column}"
        ORDER BY message_count DESC
    '''
    return [dict(row) for row in conn.execute(sql).fetchall()]


def export_conversations(signal_dir: Path) -> dict[str, Any]:
    db_copy = copy_database(signal_dir)
    try:
        key = decrypt_signal_db_key(signal_dir)
        with open_signal_database(db_copy, key) as conn:
            tables = list_tables(conn)
            if "conversations" in tables:
                source = "conversations"
                conversations = export_from_conversations(conn)
            elif "messages" in tables:
                source = "messages"
                conversations = export_from_messages(conn)
            else:
                raise RuntimeError("Could not find a conversations or messages table in the Signal database.")

        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "signal_dir": str(signal_dir),
            "source_table": source,
            "conversation_count": len(conversations),
            "conversations": conversations,
        }
    finally:
        shutil.rmtree(db_copy.parent, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Signal Desktop conversation IDs to JSON.")
    parser.add_argument("--signal-dir", type=Path, default=DEFAULT_SIGNAL_DIR, help="Path to the Signal Desktop profile.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON output path.")
    args = parser.parse_args()

    data = export_conversations(args.signal_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)

    print(f"Wrote {data['conversation_count']} conversations to {args.output}")


if __name__ == "__main__":
    main()
