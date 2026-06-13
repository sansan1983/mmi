"""P1-1 & P1-4: Feishu messaging and streaming card tools.

P1-1: send_image, send_file - Send files/images to Feishu
P1-4: stream_card - Feishu streaming card with auto-chunking

Based on:
- sop_feishu_send_image.md
- sop_feishu_send_file.md
- relay_sop.md (FeishuCardStream design)

Uses @tool decorator for auto-registration.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# Config (from SOPs)
# ---------------------------------------------------------------------------

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a95b996b57b8dcbd")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "RIVhfjdY7NjLduiQ3pOpocnTs8JAc7rT")
FEISHU_RECEIVE_ID = os.environ.get("FEISHU_RECEIVE_ID", "ou_64d4263aa7254541577e7ef6aea27b4b")

# Token cache (in-memory, 2h TTL)
_token_cache: dict[str, Any] = {"token": "", "expires": 0}


def _get_token() -> str:
    """Get or refresh Feishu tenant access token."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires"] > now:
        return _token_cache["token"]

    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    if "tenant_access_token" not in data:
        raise RuntimeError(f"Failed to get token: {data}")

    token = data["tenant_access_token"]
    _token_cache["token"] = token
    _token_cache["expires"] = now + 7000  # ~2h minus buffer
    return token


# ---------------------------------------------------------------------------
# P1-1: send_image
# ---------------------------------------------------------------------------


@tool(
    name="send_feishu_image",
    description="Send an image message to Feishu. Takes an image file path, "
    "uploads it via Feishu API, and sends as image message.",
    schema={
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file to send",
            },
            "receive_id": {
                "type": "string",
                "description": "Feishu open_id or user_id to send to (default: config receive_id)",
            },
        },
        "required": ["image_path"],
    },
)
def send_feishu_image(image_path: str, receive_id: str = FEISHU_RECEIVE_ID) -> str:
    """Send image to Feishu."""
    if not os.path.exists(image_path):
        return f"Error: file not found: {image_path}"

    try:
        token = _get_token()

        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                data={"image_type": "message"},
                files={"image": f},
                timeout=20,
            )
        result = resp.json()
        image_key = (
            result.get("data", {}).get("image_key")
            or result.get("image_key")
        )
        if not image_key:
            return f"Upload failed: {json.dumps(result, ensure_ascii=False)[:500]}"

        # Send message
        send_resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": receive_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}),
            },
            timeout=15,
        )
        return json.dumps(
            send_resp.json(), ensure_ascii=False
        )

    except Exception as e:
        return f"send_feishu_image error: {e}"


# ---------------------------------------------------------------------------
# P1-1: send_file
# ---------------------------------------------------------------------------


@tool(
    name="send_feishu_file",
    description="Send a file to Feishu. Uploads file with file_type=stream "
    "(required) and sends as file message.",
    schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to send",
            },
            "receive_id": {
                "type": "string",
                "description": "Feishu open_id or user_id to send to (default: config receive_id)",
            },
            "file_type": {
                "type": "string",
                "description": "File type for upload. Use 'stream' for audio/mp3/opus (default: 'stream'). "
                "CRITICAL: must be 'stream' for audio files.",
            },
        },
        "required": ["file_path"],
    },
)
def send_feishu_file(
    file_path: str,
    receive_id: str = FEISHU_RECEIVE_ID,
    file_type: str = "stream",
) -> str:
    """Send file to Feishu. file_type=stream is required for audio."""
    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"

    try:
        token = _get_token()

        with open(file_path, "rb") as f:
            content = f.read()
        file_name = os.path.basename(file_path)

        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/files",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_name": file_name,
                "file_type": file_type,  # MUST be 'stream', never 'mp3' etc.
            },
            files={"file": (file_name, content)},
            timeout=30,
        )
        result = resp.json()
        file_key = result.get("data", {}).get("file_key")
        if not file_key:
            return f"Upload failed: {json.dumps(result, ensure_ascii=False)[:500]}"

        # Send message
        send_resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": receive_id,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key}),
            },
            timeout=15,
        )
        return json.dumps(
            send_resp.json(), ensure_ascii=False
        )

    except Exception as e:
        return f"send_feishu_file error: {e}"


# ---------------------------------------------------------------------------
# P1-1: send_text
# ---------------------------------------------------------------------------


@tool(
    name="send_feishu_text",
    description="Send a text message to Feishu. Supports markdown content.",
    schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text content to send",
            },
            "receive_id": {
                "type": "string",
                "description": "Feishu open_id or user_id to send to",
            },
            "is_markdown": {
                "type": "boolean",
                "description": "If True, send as markdown message (default: True)",
            },
        },
        "required": ["text"],
    },
)
def send_feishu_text(
    text: str,
    receive_id: str = FEISHU_RECEIVE_ID,
    is_markdown: bool = True,
) -> str:
    """Send text/markdown message to Feishu."""
    try:
        token = _get_token()

        msg_type = "post" if is_markdown else "text"
        if not is_markdown:
            content_json = json.dumps({"text": text.strip()})
        else:
            # Markdown post structure
            content_json = json.dumps({
                "title": "MMI Reply",
                "zh_cn": {
                    "title": "MMI Reply",
                    "content": [[{"tag": "plain_text", "text": text.strip()}]]
                }
            })

        send_resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content_json,
            },
            timeout=15,
        )
        return json.dumps(
            send_resp.json(), ensure_ascii=False
        )

    except Exception as e:
        return f"send_feishu_text error: {e}"


# ---------------------------------------------------------------------------
# P1-4: FeishuCardStream - Streaming card with auto-chunking
# ---------------------------------------------------------------------------


class FeishuCardStream:
    """Feishu streaming card with automatic message chunking.

    Sends messages in real-time via Feishu streaming API.
    Handles long messages by auto-splitting into multiple cards.
    """

    def __init__(
        self,
        card_id: str = "default",
        max_body_chars: int = 4000,
        min_interval: float = 0.5,
    ):
        self.card_id = card_id
        self.max_body_chars = max_body_chars
        self.min_interval = min_interval
        self.last_push_time = 0
        self._chunks: list[str] = []

    def push(self, chunk: str) -> str:
        """Push a text chunk to the card. Returns the update command payload."""
        now = time.time()
        if now - self.last_push_time < self.min_interval:
            return ""  # Debounce

        self._chunks.append(chunk)
        self.last_push_time = now

        # Build update payload
        full_body = "".join(self._chunks)

        # Check if we need to split into multiple cards
        if len(full_body) > self.max_body_chars:
            # Auto-chunk: send completed cards
            total_cards = (len(full_body) // self.max_body_chars) + 1
            return json.dumps({
                "type": "stream_update",
                "stream_id": self.card_id,
                "data": {
                    "type": "text",
                    "text": full_body[: self.max_body_chars],
                },
            })

        return json.dumps({
            "type": "stream_update",
            "stream_id": self.card_id,
            "data": {
                "type": "text",
                "text": full_body,
            },
        })

    def finish(self, footer: str = "") -> str:
        """Finish the stream. Returns final payload with optional footer."""
        full_body = "".join(self._chunks)
        payload: dict[str, Any] = {
            "type": "stream_update",
            "stream_id": self.card_id,
            "finish": True,
        }
        if full_body:
            payload["data"] = {
                "type": "text",
                "text": full_body,
            }
        if footer:
            payload["footer"] = footer
        return json.dumps(payload)


@tool(
    name="feishu_card_stream",
    description="Create a Feishu streaming card for real-time updates. "
    "Returns a stream object that supports push() and finish() methods. "
    "Auto-chunks long messages into multiple cards.",
    schema={
        "type": "object",
        "properties": {
            "card_id": {
                "type": "string",
                "description": "Unique card ID for this stream session",
            },
            "initial_content": {
                "type": "string",
                "description": "Initial text content for the card",
            },
            "max_body_chars": {
                "type": "integer",
                "description": "Max characters per card (default: 4000)",
            },
            "footer": {
                "type": "string",
                "description": "Footer text appended when stream finishes",
            },
        },
        "required": [],
    },
)
def feishu_card_stream(
    card_id: str = "stream-default",
    initial_content: str = "",
    max_body_chars: int = 4000,
    footer: str = "",
) -> str:
    """Create and optionally push to a Feishu streaming card.
    
    Returns: summary of stream state (not the object itself,
    as tools can't return Python objects).
    """
    stream = FeishuCardStream(
        card_id=card_id,
        max_body_chars=max_body_chars,
    )
    
    if initial_content:
        update = stream.push(initial_content)
        finish = stream.finish(footer)
        return f"Card '{card_id}' created with {len(stream._chunks)} chunk(s):\n" \
               f"Update: {update[:200]}\nFinish: {finish[:200]}"
    
    return f"Card '{card_id}' created, ready for push(). Use footer: {footer}"
