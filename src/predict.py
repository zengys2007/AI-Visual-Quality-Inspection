"""按 Ultralytics YOLO 官方教程进行预测推理（实例分割）。

参考:
- 预测: https://docs.ultralytics.com/zh/modes/predict
- 分割: https://docs.ultralytics.com/zh/tasks/segment/
"""

from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
# 推荐使用完整训练得到的 best.pt
WEIGHTS = ROOT / "runs" / "segment" / "surface_crack-3" / "weights" / "best.pt"
# 待检测：单张图或文件夹
SOURCE = ROOT / "data" / "test"


if __name__ == "__main__":
    # Windows 下以脚本启动预测时建议放在 __main__ 中
    # 与训练/验证一致，在项目根目录下启动
    import os

    os.chdir(ROOT)

    if not WEIGHTS.is_file():
        raise FileNotFoundError(
            f"找不到权重: {WEIGHTS}\n请先完成训练，或修改 WEIGHTS 指向有效的 best.pt"
        )
    if not SOURCE.exists():
        raise FileNotFoundError(f"找不到输入: {SOURCE}")

    # 加载自定义训练权重
    model = YOLO(str(WEIGHTS))

    # 对目录/图片推理；stream=True 省内存（官方推荐处理大量图片时使用）
    # 有 GPU 时自动使用，否则使用 CPU
    results = model.predict(
        source=str(SOURCE),
        conf=0.25,
        imgsz=640,
        save=True,
        stream=True,
        project=str(ROOT / "runs" / "segment"),
        name="surface_crack_predict",
        exist_ok=True,
    )

    # 处理 Results：输出裂纹位置 (xyxy) 与置信度
    for result in results:
        boxes = result.boxes  # Boxes 对象
        masks = result.masks  # Masks 对象（分割）
        image_id = Path(result.path).name
        print(f"\n{image_id}")

        if boxes is None or len(boxes) == 0:
            print("  （未检出）")
            continue

        # boxes.xyxy: 像素坐标 [x_min, y_min, x_max, y_max]
        # boxes.conf: 置信度
        # boxes.cls:  类别 ID
        for xyxy, conf, cls_id in zip(boxes.xyxy, boxes.conf, boxes.cls):
            x_min, y_min, x_max, y_max = (float(v) for v in xyxy)
            name = result.names[int(cls_id)]
            print(
                f"  {name}  conf={float(conf):.2f}  "
                f"xyxy=[{x_min:.1f}, {y_min:.1f}, {x_max:.1f}, {y_max:.1f}]"
            )

        if masks is not None:
            print(f"  masks: {masks.data.shape}")  # (N, H, W)
