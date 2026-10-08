"""电池包视觉质检 — pywebview 桌面壳入口。

启动本地静态前端，窗口表现为桌面应用。本阶段检测为前端 mock，不调用 YOLO。
"""

from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "static" / "index.html"


def main() -> None:
    if not INDEX.is_file():
        raise FileNotFoundError(f"找不到界面文件: {INDEX}")

    webview.create_window(
        title="电池包视觉质检系统",
        url=INDEX.as_uri(),
        width=1440,
        height=900,
        min_size=(1100, 700),
        background_color="#E8ECF1",
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
