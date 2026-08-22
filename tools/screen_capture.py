"""Privacy-sensitive Windows screen capture for MCP image content."""

from __future__ import annotations

import base64
import io
from collections.abc import Callable
from typing import Any


class ScreenCapture:
    def __init__(self, capture_fn: Callable[[], Any] | None = None, max_width: int = 1600, max_height: int = 1200, jpeg_quality: int = 70) -> None:
        self.capture_fn = capture_fn
        self.max_width = max_width
        self.max_height = max_height
        self.jpeg_quality = jpeg_quality

    def _capture(self):
        if self.capture_fn is not None:
            return self.capture_fn()
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise RuntimeError("Pillow is not installed; run python -m pip install -r requirements.txt") from exc
        return ImageGrab.grab(all_screens=True)

    def capture(self, _arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            image = self._capture()
            image = image.convert("RGB")
            image.thumbnail((self.max_width, self.max_height))
            stream = io.BytesIO()
            image.save(stream, format="JPEG", quality=self.jpeg_quality, optimize=True)
            encoded = base64.b64encode(stream.getvalue()).decode("ascii")
            return {
                "success": True,
                "tool": "screen_capture",
                "message": "Screen captured",
                "width": image.width,
                "height": image.height,
                "mime_type": "image/jpeg",
                "content": [
                    {"type": "image", "data": encoded, "mimeType": "image/jpeg"},
                    {"type": "text", "text": f"Screen capture: {image.width}x{image.height}"},
                ],
            }
        except (OSError, RuntimeError, ValueError) as exc:
            return {"success": False, "tool": "screen_capture", "error_code": "SCREEN_CAPTURE_FAILED", "message": str(exc)}

