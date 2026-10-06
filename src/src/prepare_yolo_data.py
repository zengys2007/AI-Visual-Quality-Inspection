# -*- coding: utf-8 -*-
"""
prepare_yolo_data.py — 用测试集标注整理成 YOLO 训练数据集
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # src/src/xxx.py → 项目根
sys.path.insert(0, str(_PROJECT_ROOT))

from src.src.preprocess import enhance_crack_file     # 复用训推一致的增强函数

# ------------------------- 可调参数 -------------------------
TEST_DIR = "data/测试集"          # 原始测试集（图 + json）
YOLO_DIR = "data/yolo"            # YOLO 数据集根目录
VAL_RATIO = 0.15                  # 验证集占比
SEED = 42                         # 随机种子，划分可复现
CLASS_NAME = "Surface_Crack"      # 类别名
# ------------------------------------------------------------


def read_image_size(jpg_path: Path) -> tuple[int, int]:
    """读取图片宽高（imdecode 兼容中文路径）。"""
    data = np.fromfile(str(jpg_path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"无法读取图片: {jpg_path}")
    h, w = img.shape[:2]
    return w, h


def parse_json_boxes(json_path: Path, img_w: int, img_h: int):
    """json 多边形顶点（像素坐标）→ YOLO 矩形框 (cx, cy, w, h) 归一化列表。"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    boxes = []
    for shape in data.get("shapes", []):
        pts = shape.get("data", {}).get("points", [])
        if len(pts) < 2:
            continue
        pts = np.asarray(pts, dtype=np.float32)
        x_min, y_min = pts[:, 0].min(), pts[:, 1].min()
        x_max, y_max = pts[:, 0].max(), pts[:, 1].max()

        cx = ((x_min + x_max) / 2) / img_w
        cy = ((y_min + y_max) / 2) / img_h
        w = (x_max - x_min) / img_w
        h = (y_max - y_min) / img_h
        boxes.append((min(max(cx, 0), 1), min(max(cy, 0), 1),
                      min(max(w, 0), 1), min(max(h, 0), 1)))
    return boxes


def write_label_txt(txt_path: Path, boxes) -> None:
    """每行 `0 cx cy w h`；无目标写空文件（背景图）。"""
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cx, cy, w, h in boxes]
    txt_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    test_dir = (_PROJECT_ROOT / TEST_DIR).resolve()
    yolo_dir = (_PROJECT_ROOT / YOLO_DIR).resolve()
    enhanced_dir = yolo_dir / "images_enhanced"   # 已有增强图，优先复用

    json_files = sorted(test_dir.glob("image_*.json"))
    if not json_files:
        raise SystemExit(f"未在 {test_dir} 找到 image_*.json")

    # 划分 train / val（固定种子，可复现）
    rng = random.Random(SEED)
    rng.shuffle(json_files)
    n_val = max(1, round(len(json_files) * VAL_RATIO))
    val_names = {p.stem for p in json_files[:n_val]}
    print(f"共 {len(json_files)} 张，train={len(json_files) - n_val} / val={n_val}")

    total_boxes = 0
    for jf in json_files:
        split = "val" if jf.stem in val_names else "train"
        jpg_path = jf.with_suffix(".jpg")
        if not jpg_path.exists():
            print(f"跳过（缺 jpg）: {jf.name}")
            continue

        img_w, img_h = read_image_size(jpg_path)
        boxes = parse_json_boxes(jf, img_w, img_h)
        total_boxes += len(boxes)

        # 标签
        write_label_txt(yolo_dir / "labels" / split / f"{jf.stem}.txt", boxes)

        # 图片：优先复制已有增强图，没有则重新增强
        dst_jpg = yolo_dir / "images" / split / f"{jf.stem}.jpg"
        src_enhanced = enhanced_dir / f"{jf.stem}.jpg"
        if src_enhanced.exists():
            shutil.copy2(src_enhanced, dst_jpg)
        else:
            enhance_crack_file(jpg_path, dst_jpg)

    # data.yaml
    (yolo_dir / "data.yaml").write_text(
        f"# 由 prepare_yolo_data.py 生成\n"
        f"path: {yolo_dir.as_posix()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: 1\n"
        f"names: ['{CLASS_NAME}']\n",
        encoding="utf-8",
    )
    print(f"完成：共 {total_boxes} 个目标框；data.yaml 已生成于 {yolo_dir / 'data.yaml'}")


if __name__ == "__main__":
    main()