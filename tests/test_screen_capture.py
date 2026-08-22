import base64
import io

from PIL import Image

from tools.screen_capture import ScreenCapture


def test_screen_capture_returns_bounded_mcp_image_without_writing_file():
    source = Image.new("RGB", (2400, 1200), "red")
    capture = ScreenCapture(capture_fn=lambda: source, max_width=800, max_height=600)
    result = capture.capture({})
    assert result["success"] is True
    assert result["content"][0]["type"] == "image"
    image = Image.open(io.BytesIO(base64.b64decode(result["content"][0]["data"])))
    assert image.size == (800, 400)
    assert "path" not in result


def test_screen_capture_returns_business_error_when_capture_fails():
    capture = ScreenCapture(capture_fn=lambda: (_ for _ in ()).throw(OSError("desktop unavailable")))
    result = capture.capture({})
    assert result["success"] is False
    assert result["error_code"] == "SCREEN_CAPTURE_FAILED"
