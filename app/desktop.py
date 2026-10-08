"""电池包视觉质检 — pywebview 桌面壳入口。

启动本地静态前端，窗口表现为桌面应用。本阶段检测为前端 mock，不调用 YOLO。
"""

from __future__ import annotations

import ctypes
import struct
import sys
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "static" / "index.html"
BLANK_ICON = ROOT / "static" / "blank.ico"

# 与前端 --bg / background_color 一致
BG_HEX = "#EEF1F5"
# COLORREF: 0x00BBGGRR
BG_COLORREF = 0x00F5F1EE


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


def main() -> None:
    if not INDEX.is_file():
        raise FileNotFoundError(f"找不到界面文件: {INDEX}")

    icon = _ensure_blank_icon()
    window = webview.create_window(
        title="",
        url=INDEX.as_uri(),
        width=1440,
        height=900,
        min_size=(1100, 700),
        background_color=BG_HEX,
    )

    events = getattr(window, "events", None)
    if events is not None and hasattr(events, "before_show"):
        events.before_show += _style_window_chrome
    elif hasattr(window, "before_show"):
        window.before_show += _style_window_chrome

    webview.start(debug=False, icon=str(icon))


if __name__ == "__main__":
    main()
