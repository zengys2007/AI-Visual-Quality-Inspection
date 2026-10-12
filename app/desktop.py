"""电池包视觉质检 — pywebview 桌面壳入口。

启动本地静态前端，窗口表现为桌面应用。检测权重需用户在界面选择 .pt 文件。
支持从资源管理器 / 桌面拖入图像文件或文件夹。
"""

from __future__ import annotations

import base64
import binascii
import ctypes
import io
import json
import mimetypes
import struct
import sys
import threading
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
INDEX = ROOT / "static" / "index.html"
BLANK_ICON = ROOT / "static" / "blank.ico"

# 与 src/predict.py 保持一致
CONF = 0.19
IMGSZ = 640
ALLOWED_WEIGHT_EXTS = {".pt"}

# 与前端 --bg / background_color 一致（按系统浅/深色解析）
BG_DAY_HEX = "#EEF1F5"
BG_NIGHT_HEX = "#1E1E24"
# COLORREF: 0x00BBGGRR
BG_DAY_COLORREF = 0x00F5F1EE
BG_NIGHT_COLORREF = 0x00241E1E
BG_DAY_RGB = (0xEE, 0xF1, 0xF5)
BG_NIGHT_RGB = (0x1E, 0x1E, 0x24)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _system_prefers_dark() -> bool:
    """读取 Windows 应用浅色主题开关；非 Windows 或读取失败则浅色。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except OSError:
        return False


def _resolve_window_bg() -> tuple[str, int, tuple[int, int, int]]:
    """按系统主题返回 (hex, COLORREF, RGB)，供窗口与 DWM 着色一致。"""
    if _system_prefers_dark():
        return BG_NIGHT_HEX, BG_NIGHT_COLORREF, BG_NIGHT_RGB
    return BG_DAY_HEX, BG_DAY_COLORREF, BG_DAY_RGB


class Api:
    """前端 JS 桥：YOLO 检测 + 保存符合接口规范的检测结果 CSV。"""

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._model = None  # Ultralytics YOLO 实例，选权重后加载
        self._weights_path: Path | None = None
        self._conf = float(CONF)  # 当前置信度阈值，默认 0.223，可被前端手动覆盖
        self._model_lock = threading.Lock()  # 加载与推理互斥，避免并发换模
        self._load_error: str | None = None

    def bind(self, window: webview.Window) -> None:
        """挂接主窗口，供文件对话框与拖放使用。"""
        self._window = window

    def get_engine_status(self) -> dict:
        """供前端显示当前推理引擎状态。"""
        weights = self._weights_path
        return {
            "mode": "yolo",
            "weights": str(weights) if weights else "",
            "weights_name": weights.name if weights else "",
            "weights_ok": bool(weights and weights.is_file()),
            "conf": self._conf,
            "imgsz": IMGSZ,
            "model_loaded": self._model is not None,
            "load_error": self._load_error,
            "need_weights": self._model is None,
        }

    def set_conf(self, value) -> dict:
        """更新检测置信度阈值（0~1）。"""
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return {"ok": False, "error": "置信度必须是数字", "conf": self._conf}
        if not 0.0 <= conf <= 1.0:
            return {"ok": False, "error": "置信度需在 0 ~ 1 之间", "conf": self._conf}
        self._conf = round(conf, 3)
        return {"ok": True, "conf": self._conf}

    def choose_weights(self) -> dict:
        """弹出文件管理器选择 .pt 权重并加载。"""
        if self._window is None:
            return {"ok": False, "error": "window not ready"}

        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            directory=str(PROJECT_ROOT),
            allow_multiple=False,
            file_types=("PyTorch Weights (*.pt)", "All files (*.*)"),
        )
        if not result:
            return {"ok": False, "cancelled": True}

        path = Path(result if isinstance(result, str) else result[0])
        suffix = path.suffix.lower()
        if suffix not in ALLOWED_WEIGHT_EXTS:
            shown = suffix if suffix else "（无扩展名）"
            return {
                "ok": False,
                "invalid_type": True,
                "error": f"不支持的文件类型：{shown}。请选择 .pt 权重文件。",
                "path": str(path),
                "name": path.name,
            }
        if not path.is_file():
            return {"ok": False, "error": f"文件不存在: {path}"}

        try:
            from ultralytics import YOLO

            with self._model_lock:
                model = YOLO(str(path))
                self._model = model
                self._weights_path = path
                self._load_error = None
            return {
                "ok": True,
                "weights": str(path),
                "name": path.name,
                "conf": self._conf,
                "imgsz": IMGSZ,
            }
        except Exception as exc:  # noqa: BLE001 — 透传给前端
            self._load_error = str(exc)
            with self._model_lock:
                self._model = None
            return {"ok": False, "error": str(exc)}

    def detect_image(self, payload: dict | None = None) -> dict:
        """对单张图做 YOLO 推理，返回与接口规范一致的 records。

        payload 支持 path（本地绝对路径）或 dataUrl（base64）；
        可选 conf 覆盖当前阈值。无检出时 records 含一行 Ok 占位。
        """
        data = payload if isinstance(payload, dict) else {}
        name = str(data.get("name") or "image.jpg")
        path_raw = data.get("path")
        data_url = data.get("dataUrl")
        # 优先用请求内 conf，否则用 Api 当前阈值
        conf = self._conf
        if data.get("conf") is not None:
            try:
                conf = float(data.get("conf"))
            except (TypeError, ValueError):
                conf = self._conf
            conf = min(1.0, max(0.0, conf))

        try:
            model = self._ensure_model()
            source = self._resolve_source(path_raw, data_url)
            results = model.predict(
                source=source,
                conf=conf,
                imgsz=IMGSZ,
                verbose=False,
            )
            result = results[0]
            records = self._records_for_image(result, name)
            # 首行 Ok 视为合格，否则 NG（有裂纹实例）
            verdict = "ok" if records and records[0]["class_name"] == "Ok" else "ng"
            inference_ms = records[0]["inference_time_ms"] if records else 0.0
            return {
                "ok": True,
                "verdict": verdict,
                "inferenceMs": inference_ms,
                "records": records,
            }
        except Exception as exc:  # noqa: BLE001 — 透传给前端
            return {"ok": False, "error": str(exc)}

    def save_csv(self, content: str, filename: str) -> dict:
        """弹出另存为对话框，以 UTF-8 写入 CSV。"""
        if self._window is None:
            return {"ok": False, "error": "window not ready"}

        default_name = filename or "兴欣_检测结果.csv"
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

    def _ensure_model(self):
        """返回已加载模型；未选权重时抛错提示前端引导选择。"""
        with self._model_lock:
            if self._model is not None:
                return self._model
            raise FileNotFoundError("尚未选择权重文件，请先点击右上角选择 .pt 权重")

    @staticmethod
    def _resolve_source(path_raw, data_url):
        """优先本地路径；否则解码 dataUrl 为 PIL RGB 图供 YOLO 推理。"""
        if path_raw:
            path = Path(str(path_raw))
            if path.is_file():
                return str(path)
        if not data_url:
            raise ValueError("缺少图像数据（path 或 dataUrl）")
        text = str(data_url)
        # data:image/...;base64,XXXX → 只取逗号后载荷
        if "," in text:
            text = text.split(",", 1)[1]
        try:
            raw = base64.b64decode(text, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"无法解码图像 dataUrl: {exc}") from exc
        from PIL import Image

        return Image.open(io.BytesIO(raw)).convert("RGB")

    @staticmethod
    def _inference_time_ms(result) -> float:
        """整张图耗时 = 预处理 + 推理 + 后处理（毫秒）。"""
        speed = result.speed or {}
        return float(
            speed.get("preprocess", 0)
            + speed.get("inference", 0)
            + speed.get("postprocess", 0)
        )

    @classmethod
    def _polygon_for_index(cls, result, index: int) -> list[list[float]] | None:
        """提取实例分割轮廓像素坐标，供前端按裂纹形态绘制。"""
        masks = getattr(result, "masks", None)
        if masks is None:
            return None
        xy_list = getattr(masks, "xy", None)
        if xy_list is None or index >= len(xy_list):
            return None
        poly = xy_list[index]
        if poly is None or len(poly) < 3:
            return None
        return [[round(float(x), 1), round(float(y), 1)] for x, y in poly]

    @classmethod
    def _records_for_image(cls, result, image_id: str) -> list[dict]:
        """将 YOLO 结果转为接口规范行：有框多行；无框一行 Ok（坐标填 -1）。"""
        t_ms = round(cls._inference_time_ms(result), 1)
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            # 无缺陷占位行，保证测试图可被评分工具完整统计
            return [
                {
                    "image_id": image_id,
                    "class_name": "Ok",
                    "confidence": -1,
                    "x_min": -1,
                    "y_min": -1,
                    "x_max": -1,
                    "y_max": -1,
                    "inference_time_ms": t_ms,
                    "polygon": None,
                }
            ]

        rows: list[dict] = []
        for idx, (xyxy, conf, cls_id) in enumerate(
            zip(boxes.xyxy, boxes.conf, boxes.cls)
        ):
            x_min, y_min, x_max, y_max = (float(v) for v in xyxy)
            name = result.names[int(cls_id)]
            rows.append(
                {
                    "image_id": image_id,
                    "class_name": name,
                    "confidence": round(float(conf), 2),
                    "x_min": round(x_min, 1),
                    "y_min": round(y_min, 1),
                    "x_max": round(x_max, 1),
                    "y_max": round(y_max, 1),
                    "inference_time_ms": t_ms,  # 同图多行共用整图耗时
                    "polygon": cls._polygon_for_index(result, idx),
                }
            )
        return rows


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

    _, bg_colorref, bg_rgb = _resolve_window_bg()

    # DWMWA_BORDER_COLOR=34, DWMWA_CAPTION_COLOR=35（需 Windows 11）
    try:
        dwmapi = ctypes.windll.dwmapi
        color = ctypes.c_uint32(bg_colorref)
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

            r, g, b = bg_rgb
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
    """把本地图像编码为前端 importDroppedImages 所需结构。"""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    st = path.stat()
    return {
        "name": path.name,
        "size": st.st_size,
        "lastModified": int(st.st_mtime * 1000),
        "path": str(path.resolve()),
        "dataUrl": f"data:{mime};base64,{data}",
    }


def _push_images_to_frontend(window, paths: list[Path]) -> None:
    """通过 evaluate_js 将拖入图像列表交给前端；失败则写状态栏。"""
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


# 前端拖放视觉反馈：用 depth 抵消子元素 enter/leave 抖动，挂 is-dragging 样式
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
        # pywebview 在 files[].pywebviewFullPath 提供本地绝对路径
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
    """创建 pywebview 窗口、挂接 JS API / 拖放 / 窗口样式后进入事件循环。"""
    if not INDEX.is_file():
        raise FileNotFoundError(f"找不到界面文件: {INDEX}")

    icon = _ensure_blank_icon()
    api = Api()
    bg_hex, _, _ = _resolve_window_bg()
    window = webview.create_window(
        title="",
        url=INDEX.as_uri(),
        width=1440,
        height=900,
        min_size=(1100, 700),
        background_color=bg_hex,
        js_api=api,
    )
    api.bind(window)

    # 兼容不同 pywebview 版本的事件挂载点
    events = getattr(window, "events", None)
    if events is not None and hasattr(events, "before_show"):
        events.before_show += _style_window_chrome
    elif hasattr(window, "before_show"):
        window.before_show += _style_window_chrome

    def on_loaded() -> None:
        _bind_drag_drop(window)
        # 启动时尚未选权重，通知前端显示引导状态
        window.evaluate_js(
            "window.onEngineReady && window.onEngineReady("
            '{"ok": false, "need_weights": true}'
            ")"
        )

    if events is not None and hasattr(events, "loaded"):
        events.loaded += on_loaded
    elif hasattr(window, "loaded"):
        window.loaded += on_loaded

    webview.start(debug=False, icon=str(icon))


if __name__ == "__main__":
    main()
