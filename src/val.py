"""按 Ultralytics YOLO 官方教程验证实例分割模型。

参考:
- 验证: https://docs.ultralytics.com/zh/modes/val
- 分割: https://docs.ultralytics.com/zh/tasks/segment/
"""

from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
DATA_YAML = ROOT / "configs" / "data.yaml"
# 推荐使用完整训练得到的 best.pt
WEIGHTS = ROOT / "runs" / "segment" / "surface_crack-3" / "weights" / "best.pt"


if __name__ == "__main__":
    # Windows 下以脚本启动验证时必须放在 __main__ 中，避免多进程 RuntimeError
    # data.yaml 中 path 相对于当前工作目录，需在项目根目录下启动
    import os

    os.chdir(ROOT)

    if not WEIGHTS.is_file():
        raise FileNotFoundError(
            f"找不到权重: {WEIGHTS}\n请先完成训练，或修改 WEIGHTS 指向有效的 best.pt"
        )

    # 加载自定义训练权重；模型会记住训练时的 data / imgsz 等设置
    model = YOLO(str(WEIGHTS))

    # 在自定义数据集上验证；显式传入 data 以便覆盖/确认路径
    # 有 GPU 时自动使用，否则使用 CPU
    metrics = model.val(
        data=str(DATA_YAML),
        imgsz=640,
        batch=16,
        split="val",
        plots=True,
        project=str(ROOT / "runs" / "segment"),
        name="surface_crack_val",
        exist_ok=True,
    )

    # Box 指标（外接框）
    print("── Box ──")
    print(f"mAP50-95: {metrics.box.map:.4f}")
    print(f"mAP50:    {metrics.box.map50:.4f}")
    print(f"mAP75:    {metrics.box.map75:.4f}")
    print(f"maps:     {metrics.box.maps}")

    # Mask 指标（实例分割）
    print("── Mask ──")
    print(f"mAP50-95: {metrics.seg.map:.4f}")
    print(f"mAP50:    {metrics.seg.map50:.4f}")
    print(f"mAP75:    {metrics.seg.map75:.4f}")
    print(f"maps:     {metrics.seg.maps}")
