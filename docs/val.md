# YOLO 实例分割验证说明

在训练完成后，用 Val 模式评估 `best.pt` 在验证集上的 Box / Mask 指标。

验证集目录为 `data/test/`（由 `configs/data.yaml` 的 `val` 指定）。

| 划分 | 路径 | 说明 |
| --- | --- | --- |
| val | `data/test/` | 验证集（图片与同名 `.txt` 多边形标注） |

官方文档：[验证模式](https://docs.ultralytics.com/zh/modes/val)

## 验证前检查

1. 已完成训练，存在可用权重（推荐 `runs/segment/surface_crack-3/weights/best.pt`）
2. 验证集在 `data/test/`，图片与同名 `.txt` 标注齐全
3. `configs/data.yaml` 中 `val` → `test`
4. 已安装依赖（项目虚拟环境中需有 `ultralytics`）

## 开始验证

在项目根目录执行：

```bash
.\.venv\Scripts\python.exe src\val.py
```

有 GPU 时自动使用 GPU，否则用 CPU。

## 验证配置

脚本：`src/val.py`

| 项 | 当前值 | 说明 |
| --- | --- | --- |
| 权重 | `runs/segment/surface_crack-3/weights/best.pt` | 完整训练得到的最佳权重 |
| 数据 | `configs/data.yaml` | 使用其中的 `val` 划分 |
| imgsz | `640` | 与训练一致 |
| batch | `16` | 显存不足可改为 `4` 或 `2` |
| split | `val` | 验证划分 |
| plots | `True` | 保存 PR / F1 / 混淆矩阵等图 |
| 输出目录 | `runs/segment/surface_crack_val/` | 验证曲线与可视化 |

如需换权重，编辑 `src/val.py` 里的 `WEIGHTS`。

## 指标含义

终端会打印 Box（外接框）与 Mask（实例分割）两类指标：

| 指标 | 含义 |
| --- | --- |
| mAP50 | IoU=0.5 时的平均精度 |
| mAP75 | IoU=0.75 时的平均精度（更严） |
| mAP50-95 | IoU 从 0.5 到 0.95 的平均 mAP |

一次实测参考（160 张图，2073 个实例，`surface_crack-3/best.pt`）：

| 指标 | Box | Mask |
| --- | --- | --- |
| mAP50 | 0.523 | 0.409 |
| mAP50-95 | 0.253 | 0.106 |
| mAP75 | 0.227 | 0.010 |

## 验证结果在哪

```text
runs/segment/surface_crack_val/
  BoxPR_curve.png / BoxF1_curve.png / ...
  MaskPR_curve.png / MaskF1_curve.png / ...
  confusion_matrix.png
  val_batch*_labels.jpg   ← 真实标注
  val_batch*_pred.jpg     ← 模型预测
```

## 常见问题

- **找不到权重**：确认 `WEIGHTS` 路径存在；或先按 [train.md](./train.md) 完成训练。
- **Windows 多进程报错**：验证代码必须在 `if __name__ == "__main__":` 内（当前脚本已包含）。
- **找不到图片 / 标签为空**：确认 `data/test/` 下图片与同名 `.txt` 齐全，且与 `configs/data.yaml` 一致。
- **指标异常偏低**：检查标注是否为有效多边形；空 `.txt` 会被当成无目标。
- **显存不足**：在 `model.val(...)` 中把 `batch` 改为 `4` 或 `2`。
