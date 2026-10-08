"""按 Ultralytics YOLO 官方教程训练实例分割模型（多边形标注）。

参考:
- 训练: https://docs.ultralytics.com/zh/modes/train
- 分割: https://docs.ultralytics.com/zh/tasks/segment/
"""

from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]

# ── 配置（路径均为项目根下的绝对路径）─────────────────
# 输入
DATA_YAML = ROOT / "configs" / "data.yaml"
PRETRAINED = "yolo26n-seg.pt"  # 预训练分割模型（*-seg）

# 训练参数
EPOCHS = 100
IMGSZ = 640

# 输出
PROJECT = ROOT / "runs" / "segment"
NAME = "surface_crack"
EXIST_OK = True
# ─────────────────────────────────────────────────────


if __name__ == "__main__":
    # Windows 下以脚本启动训练时必须放在 __main__ 中，避免多进程 RuntimeError
    # data.yaml 中 path 相对当前工作目录，需在项目根目录下启动
    import os

    os.chdir(ROOT)

    model = YOLO(PRETRAINED)

    # 有 GPU 时自动使用 device=0，否则使用 CPU
    results = model.train(
        data=str(DATA_YAML),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        project=str(PROJECT),
        name=NAME,
        exist_ok=EXIST_OK,
    )
