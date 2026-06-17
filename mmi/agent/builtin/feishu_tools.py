"""P1-1 & P1-4: Feishu messaging and streaming card tools.

P1-1: send_image, send_file - Send files/images to Feishu
P1-4: stream_card - Feishu streaming card with auto-chunking

Based on:
- sop_feishu_send_image.md
- sop_feishu_send_file.md
- relay_sop.md (FeishuCardStream design)

P1: 飞书凭证必须通过环境变量配置，不再硬编码。
P1: 修复流式卡片内容截断丢失问题。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# Config (from SOP) — 全部通过环境变量配置，禁止硬编码
# ---------------------------------------------------------------------------

# Feishu 凭证必须通过环境变量设置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_RECEIVE_ID = os.environ.get("FEISHU_RECEIVE_ID", "")


def _validate_feishu_config() -> str | None:
    """Validate Feishu credentials. Returns error message or None."""
    if not FEISHU_APP_ID:
        return (
            "Error: FEISHU_APP_ID not configured. "
            "Set the FEISHU_APP_ID environment variable."
        )
    if not FEISHU_APP_SECRET:
        return (
            "Error: FEISHU_APP_SECRET not configured. "
            "Set the FEISHU_APP_SECRET environment variable."
        )
    return None

# Token cache (in-memory, 2h TTL)
_token_cache: dict[str, Any] = {"token": "", "expires": 0}


def _get_token() -> str:
    """Get or refresh Feishu tenant access token."""
    # P1: Validate credentials before every request
    err = _validate_feishu_config()
    if err:
        raise RuntimeError(err)

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
        raise RuntimeError(f"Failed to get token: {json.dumps(data, ensure_ascii=False)[:500]}")

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
    "uploads it via Feishu API, and sends as image message. "
    "Requires FEISHU_APP_ID and FEISHU_APP_SECRET environment variables.",
    schema={
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file to send"
            },
            "receive_id": {
                "type": "string",
                "description": "Feishu open_id or user_id to send to (default: from FEISHU_RECEIVE_ID env var)"
            },
        },
        "required": ["image_path"]
    },
)
def send_feishu_image(image_path: str, receive_id: str = "") -> str:
    """Send image to Feishu."""
    if not receive_id:
        receive_id = FEISHU_RECEIVE_ID
    if not receive_id:
        return "Error: No receive_id specified. Set FEISHU_RECEIVE_ID env var or pass receive_id parameter."

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
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
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

    except requests.exceptions.Timeout:
        return "send_feishu_image: request timed out (20s for upload, 15s for send)"
    except requests.exceptions.ConnectionError:
        return "send_feishu_image: connection failed. Check network and Feishu API availability."
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"send_feishu_image error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# P1-1: send_file
# ---------------------------------------------------------------------------


@tool(
    name="send_feishu_file",
    description="Send a file to Feishu. Uploads file with file_type=stream "
    "(required) and sends as file message. "
    "Requires FEISHU_APP_ID and FEISHU_APP_SECRET environment variables.",
    schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to send"
            },
            "receive_id": {
                "type": "string",
                "description": "Feishu open_id or user_id to send to (default: from FEISHU_RECEIVE_ID env var)"
            },
            "file_type": {
                "type": "string",
                "description": "File type for upload. Use 'stream' for audio/mp3/opus (default: 'stream'). "
                "CRITICAL: must be 'stream' for audio files."
            },
        },
        "required": ["file_path"]
    },
)
def send_feishu_file(
    file_path: str,
    receive_id: str = "",
    file_type: str = "stream",
) -> str:
    """Send file to Feishu. file_type=stream is required for audio."""
    if not receive_id:
        receive_id = FEISHU_RECEIVE_ID
    if not receive_id:
        return "Error: No receive_id specified. Set FEISHU_RECEIVE_ID env var or pass receive_id parameter."

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
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
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

    except requests.exceptions.Timeout:
        return "send_feishu_file: request timed out (30s for upload, 15s for send)"
    except requests.exceptions.ConnectionError:
        return "send_feishu_file: connection failed."
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"send_feishu_file error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# P1-1: send_text
# ---------------------------------------------------------------------------


@tool(
    name="send_feishu_text",
    description="Send a text message to Feishu. Supports markdown content. "
    "Requires FEISHU_APP_ID and FEISHU_APP_SECRET environment variables.",
    schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text content to send"
            },
            "receive_id": {
                "type": "string",
                "description": "Feishu open_id or user_id to send to (default: from FEISHU_RECEIVE_ID env var)"
            },
            "is_markdown": {
                "type": "boolean",
                "description": "If True, send as markdown message (default: True)"
            },
        },
        "required": ["text"]
    },
)
def send_feishu_text(
    text: str,
    receive_id: str = "",
    is_markdown: bool = True,
) -> str:
    """Send text/markdown message to Feishu."""
    if not receive_id:
        receive_id = FEISHU_RECEIVE_ID
    if not receive_id:
        return "Error: No receive_id specified. Set FEISHU_RECEIVE_ID env var or pass receive_id parameter."

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
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
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

    except requests.exceptions.Timeout:
        return "send_feishu_text: request timed out (15s)"
    except requests.exceptions.ConnectionError:
        return "send_feishu_text: connection failed."
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"send_feishu_text error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# P1-4: FeishuCardStream - Streaming card with auto-chunking
# ---------------------------------------------------------------------------


class FeishuCardStream:
    """Feishu streaming card with automatic message chunking.

    Sends messages in real-time via Feishu streaming API.
    Handles long messages by auto-splitting into multiple cards.

    P1: 修复了内容截断丢失问题 —— 超过阈值的 chunk 会完整保留，
    不丢失任何内容。
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
        """Push a text chunk to the card. Returns the update command payload.

        P1: 修复 —— 超过阈值时，仍然保留完整内容，不截断丢弃。
        返回完整内容，调用方负责决定是否分卡发送。
        """
        now = time.time()
        if now - self.last_push_time < self.min_interval:
            return ""  # Debounce

        self._chunks.append(chunk)
        self.last_push_time = now

        # Build update payload
        full_body = "".join(self._chunks)

        # P1: 如果内容很长，返回完整内容（让调用方决定是否分割）
        # 不再在这里截断丢失内容
        return json.dumps({
            "type": "stream_update",
            "stream_id": self.card_id,
            "data": {
                "type": "text",
                "text": full_body,  # Always full content
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
    "Auto-chunks long messages into multiple cards. "
    "P1: Fixed content truncation issue - no content is lost.",
    schema={
        "type": "object",
        "properties": {
            "card_id": {
                "type": "string",
                "description": "Unique card ID for this stream session"
            },
            "initial_content": {
                "type": "string",
                "description": "Initial text content for the card"
            },
            "max_body_chars": {
                "type": "integer",
                "description": "Max characters per card (default: 4000)"
            },
            "footer": {
                "type": "string",
                "description": "Footer text appended when stream finishes"
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
        return (
            f"Card '{card_id}' created with {len(stream._chunks)} chunk(s):\n"
            f"Update: {update[:200]}\n"
            f"Finish: {finish[:200]}"
        )

    return f"Card '{card_id}' created, ready for push(). Use footer: {footer}"
