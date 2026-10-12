# AI-Visual-Quality-Inspection

基于 YOLO 的表面裂纹分割项目。

## 数据位置

```text
data/yolo/
  images/train/   训练图片
  labels/train/   训练标注
  images/val/     测试（验证）图片
  labels/val/     测试（验证）标注
```

## 使用

```bash
.\.venv\Scripts\python.exe src\train.py     # 训练
.\.venv\Scripts\python.exe src\val.py       # 测试
.\.venv\Scripts\python.exe src\predict.py   # 推理预测
```

预测默认使用 `runs\segment\surface_crack\weights\best.pt`，训练完成后即可直接运行。

## 运行结果

- **训练**：`runs\segment\surface_crack\`（`weights\best.pt` 最优权重、`weights\last.pt` 最后一轮、`results.csv` 指标曲线）
- **测试**：指标（mAP50、mAP50-95 等）直接打印在终端
- **预测**：`runs\segment\surface_crack_predict\`（`images\` 标注可视化图、`txt\` 分割多边形坐标、CSV 汇总）

详见 [docs](./docs/)。