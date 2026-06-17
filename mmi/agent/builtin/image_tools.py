"""P0-4: Image generation and vision tools (agnes_image, agnes_video, ocr).

参考GA的tools_schema.json中对应的定义。
使用 @tool 装饰器自动注册。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from mmi.agent.tools import tool

# ---------------------------------------------------------------------------
# tool: agnes_image
# ---------------------------------------------------------------------------


@tool(
    name="agnes_image",
    description="Generate image using Agnes AI image generation model. "
    "Use this when user asks to draw, create image, generate picture, etc.",
    schema={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the image to generate",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for saved image",
                "default": "./temp",
            },
            "model": {
                "type": "string",
                "description": "Image model",
                "default": "agnes-image-2.1-flash",
            },
        },
    },
)
def agnes_image(prompt: str, output_dir: str = "./temp", model: str = "agnes-image-2.1-flash") -> str:
    """Generate image using Agnes AI."""
    return _call_agnes_api("image", prompt=prompt, output_dir=output_dir, model=model)


# ---------------------------------------------------------------------------
# tool: agnes_video
# ---------------------------------------------------------------------------


@tool(
    name="agnes_video",
    description="Generate video using Agnes AI video generation model. "
    "Video generation is async and takes ~5 seconds.",
    schema={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the video scene",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for saved video",
                "default": "./temp",
            },
            "model": {
                "type": "string",
                "description": "Video model",
                "default": "agnes-video-v2.0",
            },
        },
    },
)
def agnes_video(prompt: str, output_dir: str = "./temp", model: str = "agnes-video-v2.0") -> str:
    """Generate video using Agnes AI."""
    return _call_agnes_api("video", prompt=prompt, output_dir=output_dir, model=model)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_agnes_api_base() -> str:
    """Get Agnes API base URL from env or default."""
    return os.environ.get("AGNES_API_BASE", "https://api.agnesai.com/v1")


def _get_agnes_api_key() -> str | None:
    """Get Agnes API key from env."""
    return os.environ.get("AGNES_API_KEY") or os.environ.get("MMI_AGNES_KEY")


def _call_agnes_api(
    kind: str,
    prompt: str,
    output_dir: str = "./temp",
    model: str = "agnes-image-2.1-flash",
) -> str:
    """Call Agnes AI API to generate image/video."""
    api_key = _get_agnes_api_key()
    if not api_key:
        return (
            "Error: Agnes API key not configured. "
            "Set AGNES_API_KEY or MMI_AGNES_KEY environment variable."
        )

    try:
        os.makedirs(output_dir, exist_ok=True)

        api_base = _get_agnes_api_base()
        endpoint = f"{api_base}/{'images' if kind == 'image' else 'videos'}/generations"

        payload = json.dumps({"prompt": prompt, "model": model}).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Extract result URL
        result_url = None
        if data.get("data") and len(data["data"]) > 0:
            result_url = data["data"][0].get("url")

        if result_url:
            # Download result
            filename = f"{kind}_{int(__import__('time').time())}.png" if kind == "image" else f"{kind}_{int(__import__('time').time())}.mp4"
            filepath = os.path.join(output_dir, filename)
            urllib.request.urlretrieve(result_url, filepath)
            return f"Generated {kind} saved to: {filepath}"

        return f"Generated {kind} successfully (no URL in response): {json.dumps(data)[:500]}"

    except urllib.error.HTTPError as e:
        return f"Error calling Agnes API (HTTP {e.code}): {e.read().decode('utf-8', errors='replace')[:500]}"
    except Exception as e:
        return f"Error generating {kind}: {e}"
