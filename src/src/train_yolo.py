# -*- coding: utf-8 -*-
"""
train_yolo.py — 训练电池包裂纹检测模型
前置：已运行 prepare_yolo_data.py；已安装 ultralytics
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO

_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # 项目根


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="训练裂纹检测模型")
    p.add_argument("--epochs", type=int, default=120, help="训练轮数")
    p.add_argument("--imgsz", type=int, default=640, help="输入尺寸")
    p.add_argument("--batch", type=int, default=16, help="批大小（显存小调 8）")
    p.add_argument("--model", type=str, default="yolo11n.pt", help="预训练权重")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    data_yaml = (_PROJECT_ROOT / "data" / "yolo" / "data.yaml").resolve()
    if not data_yaml.exists():
        raise SystemExit("未找到 data.yaml，请先运行 prepare_yolo_data.py")

    model = YOLO(args.model)   # 首次运行自动下载 yolo11n.pt
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(_PROJECT_ROOT / "outputs"),   # 输出到已有的 outputs/
        name="crack_detect",
        patience=40,            # 40 轮无提升早停，防小数据过拟合
    )
    print("训练完成，最优权重: outputs/crack_detect/weights/best.pt")


if __name__ == "__main__":
    main()