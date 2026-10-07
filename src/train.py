"""按 Ultralytics YOLO 官方教程训练实例分割模型（多边形标注）。

参考:
- 训练: https://docs.ultralytics.com/zh/modes/train
- 分割: https://docs.ultralytics.com/zh/tasks/segment/
"""

from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
DATA_YAML = ROOT / "configs" / "data.yaml"


if __name__ == "__main__":
    # Windows 下以脚本启动训练时必须放在 __main__ 中，避免多进程 RuntimeError
    # data.yaml 中 path 相对于当前工作目录，需在项目根目录下启动
    import os

    os.chdir(ROOT)

    # 加载预训练分割模型（推荐用于训练；多边形/掩码任务用 *-seg）
    model = YOLO("yolo26n-seg.pt")

    # 在自定义数据集上训练；有 GPU 时自动使用 device=0，否则使用 CPU
    results = model.train(
        data=str(DATA_YAML),
        epochs=100,
        imgsz=640,
        project=str(ROOT / "runs" / "segment"),
        name="surface_crack",
        exist_ok=True,
    )
