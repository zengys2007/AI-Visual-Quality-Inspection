# YOLO 实例分割预测说明

对图片做表面裂纹检测，并导出评分用 CSV、可视化图与多边形标注。

## 使用前

1. 项目根目录有权重文件 `best.pt`（由训练得到的 `runs/segment/surface_crack/weights/best.pt` 复制而来）
2. 已安装依赖（虚拟环境中有 `ultralytics`）
3. 准备待检测图片（单张或文件夹）

## 开始预测

1. 打开 `src/predict.py`，按需修改：

| 项 | 默认 | 说明 |
| --- | --- | --- |
| `SOURCE` | `data/yolo/images/val` | 待检测：单张图路径或文件夹 |
| `CONF` | `0.223` | 置信度阈值（F1 最优点附近） |
| `CSV_NAME` | `视觉检测团队_检测结果.csv` | 导出文件名，提交前可改成团队名 |

2. 在项目根目录执行：

```bash
.\.venv\Scripts\python.exe src\predict.py
```

有 GPU 时自动用 GPU，否则用 CPU。

## 结果在哪

```text
runs/segment/surface_crack_predict/
  ├── 视觉检测团队_检测结果.csv   ← 评分提交用（8 列）
  ├── images/                     ← 框/Mask 叠加图
  └── txt/                        ← YOLO 多边形标注（与测试集格式一致）
```

CSV 字段说明见 [接口规范.md](./接口规范.md)。

## 常见问题

- **找不到权重**：确认根目录存在 `best.pt`；或重新从 `runs/segment/surface_crack/weights/best.pt` 复制。
- **找不到输入**：检查 `SOURCE` 路径是否存在。
- **重训后要更新推理**：把新的 `best.pt` 再复制到项目根目录覆盖即可。
