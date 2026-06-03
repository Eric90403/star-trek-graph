"""
src/comic/imagegen.py — Image generation via OpenRouter (Recraft V4.1 Pro).

Single function: generate_panel(prompt, style_anchor, reference_image=None,
                                  size='2K', model='recraft/recraft-v4.1-pro')
Returns the saved PNG path and cost in dollars.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional


# Locked house style for star-trek-graph
HOUSE_STYLE = (
    "in the style of modern IDW Star Trek comic books, "
    "bright clean coloring, bold black ink linework, "
    "smooth cel-shaded color fills, professional comic art"
)


def _load_key() -> str:
    if k := os.environ.get("OPENROUTER_API_KEY", "").strip():
        return k
    env = Path.home() / ".hermes" / ".env"
    if env.exists():
        for ln in env.read_text().splitlines():
            if ln.startswith("OPENROUTER_API_KEY="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("No OpenRouter API key available")


def generate_panel(
    out_path: Path,
    prompt: str,
    style_anchor: str = HOUSE_STYLE,
    reference_image: Optional[Path] = None,
    aspect_ratio: str = "16:9",
    model: str = "recraft/recraft-v4.1-pro",
    timeout: int = 240,
) -> dict:
    """Generate one panel image. Returns dict with 'path', 'cost_usd', 'time_s'.

    aspect_ratio: '16:9' (landscape wide), '2:3' (portrait), '1:1' (square),
                  '3:2' (landscape standard), etc.
    """
    # Critical: tell Recraft NOT to draw its own balloons/captions inside the panel.
    # Without this the model invents text balloons because the prompt mentions a
    # 'comic book panel' which it associates with overlays.
    NO_TEXT = (
        ". IMPORTANT: do not include any speech balloons, word balloons, "
        "caption boxes, dialogue text, lettering, sound effects, or written "
        "text of any kind in the image. The panel must contain only the "
        "illustrated scene with no overlaid text or balloons whatsoever."
    )
    full_prompt = f"{prompt}, {style_anchor}{NO_TEXT}"

    content: list = [{"type": "text", "text": full_prompt}]
    if reference_image:
        img_b64 = base64.b64encode(Path(reference_image).read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
        })

    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image"],
        "image_config": {"aspect_ratio": aspect_ratio},
    }

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {_load_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Eric90403/star-trek-graph",
            "X-Title": "star-trek-graph comic platform",
        },
    )

    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())

    msg = data["choices"][0]["message"]
    cost = data.get("usage", {}).get("cost", 0.0)
    imgs = msg.get("images", [])
    if not imgs:
        raise RuntimeError(
            f"Image generation returned no images: {str(msg)[:200]}"
        )

    url_or_b64 = imgs[0]["image_url"]["url"]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if url_or_b64.startswith("data:"):
        b64 = url_or_b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
    else:
        import urllib.request as _u
        with _u.urlopen(url_or_b64, timeout=60) as r:
            raw = r.read()

    # Recraft frequently returns WebP bytes regardless of extension.
    # Normalize to real PNG so downstream tools (PIL, vision APIs) work.
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        from io import BytesIO
        from PIL import Image as _Img
        buf = BytesIO()
        _Img.open(BytesIO(raw)).convert("RGB").save(buf, "PNG")
        raw = buf.getvalue()
    out_path.write_bytes(raw)

    return {
        "path":     out_path,
        "cost_usd": cost,
        "time_s":   round(time.time() - t0, 1),
        "prompt":   full_prompt,
        "model":    model,
    }


__all__ = ["generate_panel", "HOUSE_STYLE"]
