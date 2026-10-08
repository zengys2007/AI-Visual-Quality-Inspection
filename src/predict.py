"""按 Ultralytics YOLO 官方教程进行预测推理（实例分割）。

参考:
- 预测: https://docs.ultralytics.com/zh/modes/predict
- 分割: https://docs.ultralytics.com/zh/tasks/segment/
- 导出: docs/接口规范.md
"""

import csv
import os
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]

# ── 配置（路径均为项目根下的绝对路径）─────────────────
# 输入
WEIGHTS = ROOT / "best.pt"
SOURCE = ROOT / "data" / "yolo" / "images" / "val"  # 单张图或文件夹

# 推理参数
CONF = 0.223
IMGSZ = 640
SAVE = True
STREAM = True  # 大量图片时省内存

# 输出目录结构:
#   runs/segment/surface_crack_predict/
#     ├── 视觉检测团队_检测结果.csv
#     ├── images/   ← 叠加可视化图
#     └── txt/      ← 与测试集同格式的多边形标注
PROJECT = ROOT / "runs" / "segment"
NAME = "surface_crack_predict"
EXIST_OK = True
IMG_DIR = "images"
TXT_DIR = "txt"
CSV_NAME = "视觉检测团队_检测结果.csv"
# ─────────────────────────────────────────────────────
CSV_HEADER = [
    "image_id",
    "class_name",
    "confidence",
    "x_min",
    "y_min",
    "x_max",
    "y_max",
    "inference_time_ms",
]


def _inference_time_ms(result) -> float:
    """整张图检测总耗时（preprocess + inference + postprocess）。"""
    speed = result.speed or {}
    return float(
        speed.get("preprocess", 0)
        + speed.get("inference", 0)
        + speed.get("postprocess", 0)
    )


def _write_yolo_txt(path: Path, result) -> None:
    """按测试集格式写多边形标注: class_id x1 y1 x2 y2 ... xn yn（归一化）。"""
    lines: list[str] = []
    masks = result.masks
    boxes = result.boxes
    if masks is not None and boxes is not None and len(masks) > 0:
        for cls_id, poly in zip(boxes.cls, masks.xyn):
            if poly is None or len(poly) == 0:
                continue
            coords = " ".join(f"{float(v):.6f}" for xy in poly for v in xy)
            lines.append(f"{int(cls_id)} {coords}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _csv_rows_for_image(result) -> list[list]:
    """按接口规范生成该图的 CSV 行（有裂纹多行；无裂纹一行 Ok）。"""
    image_id = Path(result.path).name
    t_ms = round(_inference_time_ms(result), 1)
    boxes = result.boxes

    if boxes is None or len(boxes) == 0:
        return [[image_id, "Ok", -1, -1, -1, -1, -1, t_ms]]

    rows = []
    for xyxy, conf, cls_id in zip(boxes.xyxy, boxes.conf, boxes.cls):
        x_min, y_min, x_max, y_max = (float(v) for v in xyxy)
        name = result.names[int(cls_id)]
        rows.append(
            [
                image_id,
                name,
                round(float(conf), 2),
                round(x_min, 1),
                round(y_min, 1),
                round(x_max, 1),
                round(y_max, 1),
                t_ms,
            ]
        )
    return rows


if __name__ == "__main__":
    # Windows 下以脚本启动预测时建议放在 __main__ 中
    # data.yaml 等相对路径仍依赖项目根目录，需先 chdir
    os.chdir(ROOT)

    if not WEIGHTS.is_file():
        raise FileNotFoundError(
            f"找不到权重: {WEIGHTS}\n请先完成训练，或修改 WEIGHTS 指向有效的 best.pt"
        )
    if not SOURCE.exists():
        raise FileNotFoundError(f"找不到输入: {SOURCE}")

    out_dir = PROJECT / NAME
    img_dir = out_dir / IMG_DIR
    txt_dir = out_dir / TXT_DIR
    img_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(WEIGHTS))

    # 叠加图保存到 out_dir/images/
    results = model.predict(
        source=str(SOURCE),
        conf=CONF,
        imgsz=IMGSZ,
        save=SAVE,
        stream=STREAM,
        project=str(out_dir),
        name=IMG_DIR,
        exist_ok=EXIST_OK,
    )

    csv_rows: list[list] = []
    for result in results:
        image_id = Path(result.path).name
        stem = Path(result.path).stem
        txt_path = txt_dir / f"{stem}.txt"

        _write_yolo_txt(txt_path, result)
        rows = _csv_rows_for_image(result)
        csv_rows.extend(rows)

        print(f"\n{image_id}")
        if rows[0][1] == "Ok":
            print("  （未检出）")
        else:
            for r in rows:
                print(
                    f"  {r[1]}  conf={r[2]:.2f}  "
                    f"xyxy=[{r[3]}, {r[4]}, {r[5]}, {r[6]}]"
                )
        print(f"  -> {txt_path}")

    csv_path = out_dir / CSV_NAME
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(csv_rows)

    print(f"\n输出目录: {out_dir}")
    print(f"  CSV:    {csv_path}  ({len(csv_rows)} rows)")
    print(f"  images: {img_dir}/")
    print(f"  txt:    {txt_dir}/")
