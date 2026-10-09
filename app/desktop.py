"""电池包视觉质检 — pywebview 桌面壳入口。

启动本地静态前端，窗口表现为桌面应用。本阶段检测为前端 mock，不调用 YOLO。
支持从资源管理器 / 桌面拖入图像文件或文件夹。
"""

from __future__ import annotations

import base64
import ctypes
import json
import mimetypes
import struct
import sys
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "static" / "index.html"
BLANK_ICON = ROOT / "static" / "blank.ico"

# 与前端 --bg / background_color 一致
BG_HEX = "#EEF1F5"
# COLORREF: 0x00BBGGRR
BG_COLORREF = 0x00F5F1EE

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class Api:
    """前端 JS 桥：保存符合接口规范的检测结果 CSV。"""

    def __init__(self) -> None:
        self._window: webview.Window | None = None

    def bind(self, window: webview.Window) -> None:
        self._window = window

    def save_csv(self, content: str, filename: str) -> dict:
        """弹出另存为对话框，以 UTF-8 写入 CSV。"""
        if self._window is None:
            return {"ok": False, "error": "window not ready"}

        default_name = filename or "视觉检测团队_检测结果.csv"
        if not default_name.lower().endswith(".csv"):
            default_name += ".csv"

        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=str(Path.home() / "Desktop"),
            save_filename=default_name,
            file_types=("CSV Files (*.csv)", "All files (*.*)"),
        )
        if not result:
            return {"ok": False, "cancelled": True}

        path = Path(result if isinstance(result, str) else result[0])
        path.write_text(content, encoding="utf-8", newline="\n")
        return {"ok": True, "path": str(path)}


def _ensure_blank_icon() -> Path:
    """生成全透明 .ico，用于替换默认 Python / 系统窗口图标。"""
    if BLANK_ICON.is_file():
        return BLANK_ICON

    size = 16
    xor_size = size * size * 4
    and_row = ((size + 31) // 32) * 4
    and_size = and_row * size
    image_size = 40 + xor_size + and_size

    data = struct.pack("<HHH", 0, 1, 1)
    data += struct.pack(
        "<BBBBHHII",
        size,
        size,
        0,
        0,
        1,
        32,
        image_size,
        22,
    )
    data += struct.pack(
        "<IIIHHIIIIII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        xor_size,
        0,
        0,
        0,
        0,
    )
    data += b"\x00" * xor_size
    data += b"\x00" * and_size
    BLANK_ICON.write_bytes(data)
    return BLANK_ICON


def _style_window_chrome(window) -> None:
    """清除标题栏图标，并将边框/标题栏设为与背景同色（Windows 11 DWM）。"""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.native.Handle.ToInt64())
    except Exception:
        return

    user32 = ctypes.windll.user32
    wm_seticon = 0x0080
    gwl_exstyle = -20
    ws_ex_dlgmodalframe = 0x0001
    swp_nosize = 0x0001
    swp_nomove = 0x0002
    swp_nozorder = 0x0004
    swp_framechanged = 0x0020

    user32.SendMessageW(hwnd, wm_seticon, 0, 0)  # ICON_SMALL
    user32.SendMessageW(hwnd, wm_seticon, 1, 0)  # ICON_BIG

    ex_style = user32.GetWindowLongW(hwnd, gwl_exstyle)
    user32.SetWindowLongW(hwnd, gwl_exstyle, ex_style | ws_ex_dlgmodalframe)
    user32.SetWindowPos(
        hwnd,
        0,
        0,
        0,
        0,
        0,
        swp_nomove | swp_nosize | swp_nozorder | swp_framechanged,
    )

    # DWMWA_BORDER_COLOR=34, DWMWA_CAPTION_COLOR=35（需 Windows 11）
    try:
        dwmapi = ctypes.windll.dwmapi
        color = ctypes.c_uint32(BG_COLORREF)
        for attr in (34, 35):
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                attr,
                ctypes.byref(color),
                ctypes.sizeof(color),
            )
    except Exception:
        pass

    # WinForms 客户区背景，减少边缝色差
    try:
        native = window.native
        if hasattr(native, "BackColor"):
            from System.Drawing import Color  # type: ignore

            r, g, b = 0xEE, 0xF1, 0xF5
            native.BackColor = Color.FromArgb(r, g, b)
    except Exception:
        pass


def _collect_image_paths(raw_paths: list[str]) -> list[Path]:
    """展开拖入的文件 / 文件夹为图像路径列表。"""
    found: list[Path] = []
    seen: set[str] = set()
    for raw in raw_paths:
        path = Path(raw)
        candidates: list[Path]
        if path.is_dir():
            candidates = sorted(
                p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS
            )
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            candidates = [path]
        else:
            continue
        for item in candidates:
            key = str(item.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(item)
    return found


def _path_to_payload(path: Path) -> dict[str, object]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    st = path.stat()
    return {
        "name": path.name,
        "size": st.st_size,
        "lastModified": int(st.st_mtime * 1000),
        "dataUrl": f"data:{mime};base64,{data}",
    }


def _push_images_to_frontend(window, paths: list[Path]) -> None:
    if not paths:
        window.evaluate_js(
            "window.setStatusMessage && window.setStatusMessage('未找到可导入的图像文件')"
        )
        return
    try:
        items = [_path_to_payload(p) for p in paths]
    except OSError as exc:
        msg = json.dumps(f"读取拖入文件失败: {exc}", ensure_ascii=False)
        window.evaluate_js(f"window.setStatusMessage && window.setStatusMessage({msg})")
        return
    payload = json.dumps(items, ensure_ascii=False)
    window.evaluate_js(
        f"window.importDroppedImages && window.importDroppedImages({payload})"
    )


_DRAG_FEEDBACK_JS = r"""
(function () {
  if (window.__qiDragFeedback) return;
  window.__qiDragFeedback = true;
  var depth = 0;
  function stop(e) { e.preventDefault(); e.stopPropagation(); }
  document.addEventListener('dragenter', function (e) {
    stop(e);
    depth += 1;
    document.body.classList.add('is-dragging');
  }, true);
  document.addEventListener('dragleave', function (e) {
    stop(e);
    depth = Math.max(0, depth - 1);
    if (!depth) document.body.classList.remove('is-dragging');
  }, true);
  document.addEventListener('dragover', function (e) {
    stop(e);
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  }, true);
  document.addEventListener('drop', function () {
    depth = 0;
    document.body.classList.remove('is-dragging');
  }, true);
})();
"""


def _bind_drag_drop(window) -> None:
    """注册窗口级拖放：接收桌面 / 资源管理器拖入的图像。"""

    def on_dragover(_event) -> None:
        return None

    def on_drop(event) -> None:
        files = (event or {}).get("dataTransfer", {}).get("files", []) or []
        paths = [
            f["pywebviewFullPath"]
            for f in files
            if isinstance(f, dict) and f.get("pywebviewFullPath")
        ]
        _push_images_to_frontend(window, _collect_image_paths(paths))

    window.evaluate_js(_DRAG_FEEDBACK_JS)
    doc = window.dom.document
    # prevent_default 避免 WebView 直接打开文件；drop 时由 Python 取完整路径导入
    doc.events.dragover += DOMEventHandler(on_dragover, prevent_default=True)
    doc.events.drop += DOMEventHandler(
        on_drop, prevent_default=True, stop_propagation=True
    )


def main() -> None:
    if not INDEX.is_file():
        raise FileNotFoundError(f"找不到界面文件: {INDEX}")

    icon = _ensure_blank_icon()
    api = Api()
    window = webview.create_window(
        title="",
        url=INDEX.as_uri(),
        width=1440,
        height=900,
        min_size=(1100, 700),
        background_color=BG_HEX,
        js_api=api,
    )
    api.bind(window)

    events = getattr(window, "events", None)
    if events is not None and hasattr(events, "before_show"):
        events.before_show += _style_window_chrome
    elif hasattr(window, "before_show"):
        window.before_show += _style_window_chrome

    def on_loaded() -> None:
        _bind_drag_drop(window)

    if events is not None and hasattr(events, "loaded"):
        events.loaded += on_loaded
    elif hasattr(window, "loaded"):
        window.loaded += on_loaded

    webview.start(debug=False, icon=str(icon))


if __name__ == "__main__":
    main()
