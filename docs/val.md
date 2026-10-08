# YOLO 实例分割验证说明

用训练好的权重在验证集上评估 Box / Mask 指标，并生成曲线与可视化。

验证集：`data/yolo/images/val` + `labels/val`（`configs/data.yaml` 的 `val`）。

## 使用前

1. 已完成训练，存在权重（默认读 `runs/segment/surface_crack/weights/best.pt`）
2. `data/yolo/images/val` 与 `labels/val` 下图片与同名 `.txt` 齐全
3. 已安装依赖（虚拟环境中有 `ultralytics`）

## 开始验证

1. 打开 `src/val.py`，按需修改顶部配置：

| 项 | 默认 | 说明 |
| --- | --- | --- |
| `WEIGHTS` | `runs/segment/surface_crack/weights/best.pt` | 待评估权重；也可改成根目录 `best.pt` |
| `IMGSZ` | `640` | 与训练一致 |
| `BATCH` | `16` | 显存不足改为 `4` 或 `2` |
| `NAME` | `surface_crack_val` | 输出子目录名 |
| `EXIST_OK` | `True` | `True` 覆盖同名目录 |

2. 在项目根目录执行：

```bash
.\.venv\Scripts\python.exe src\val.py
```

有 GPU 时自动用 GPU，否则用 CPU。终端会打印 Box / Mask 的 mAP。

## 结果在哪

```text
runs/segment/surface_crack_val/
  BoxPR_curve.png / BoxF1_curve.png / BoxP_curve.png / BoxR_curve.png
  MaskPR_curve.png / MaskF1_curve.png / ...
  confusion_matrix.png
  val_batch*_labels.jpg   ← 真实标注
  val_batch*_pred.jpg     ← 模型预测
```

## 指标含义

| 指标 | 含义 |
| --- | --- |
| mAP50 | IoU=0.5 时的平均精度 |
| mAP75 | IoU=0.75（更严） |
| mAP50-95 | IoU 从 0.5 到 0.95 的平均 |

一次实测参考（160 张图，`surface_crack/best.pt`）：

| 指标 | Box | Mask |
| --- | --- | --- |
| mAP50 | 0.523 | 0.409 |
| mAP50-95 | 0.253 | 0.106 |
| mAP75 | 0.227 | 0.010 |

## 常见问题

- **找不到权重**：确认 `WEIGHTS` 路径存在；或先按 [train.md](./train.md) 训练。
- **Windows 多进程报错**：须在 `if __name__ == "__main__":` 内启动（脚本已包含）。
- **找不到图片 / 标签为空**：确认 `data/yolo/images|labels/val` 与 `configs/data.yaml` 一致。
- **指标异常偏低**：检查标注是否为有效多边形；空 `.txt` 视为无目标。
