# YOLO 实例分割训练说明

训练集已就绪；验证集目录为 `data/test/`。

| 划分 | 路径 | 说明 |
| --- | --- | --- |
| train | `data/yolo/images/train` + `labels/train` | 已标注训练样本 |
| val | `data/test/` | 验证集（图片与同名 `.txt`） |

训练样本仍偏少时适合先跑通流程；后续继续标注训练集后再整理重训，效果会更好。

## 训练前检查

1. 训练集已整理到 `data/yolo/`（见 [organize_yolo_data.md](./organize_yolo_data.md)）
2. 验证集在 `data/test/`（含有效标注更佳）
3. `configs/data.yaml`：`train` → yolo，`val` → test
4. 已安装依赖（项目虚拟环境中需有 `ultralytics`）

## 开始训练

在项目根目录执行：

```bash
.\.venv\Scripts\python.exe src\train.py
```

首次运行会自动下载预训练权重 `yolo26n-seg.pt`。有 GPU 时自动使用 GPU，否则用 CPU。

## 训练配置

脚本：`src/train.py`

| 项 | 当前值 | 说明 |
| --- | --- | --- |
| 模型 | `yolo26n-seg.pt` | YOLO26 nano 分割预训练模型 |
| 数据 | `configs/data.yaml` | 自定义 Surface_Crack 数据集 |
| epochs | `100` | 训练轮数 |
| imgsz | `640` | 输入尺寸 |
| 输出目录 | `runs/segment/surface_crack/` | 权重与曲线图 |

如需改轮数等参数，直接编辑 `src/train.py` 里 `model.train(...)` 的参数。

官方文档：

- [训练模式](https://docs.ultralytics.com/zh/modes/train)
- [实例分割](https://docs.ultralytics.com/zh/tasks/segment/)

## 训练结果在哪

训练结束后主要文件：

```text
runs/segment/surface_crack/
  weights/
    best.pt    ← 验证集上最好的权重（推荐后续推理用这个）
    last.pt    ← 最后一轮权重
  results.csv / results.png
  *.jpg        ← 训练过程可视化
```

若目录已存在且不想覆盖，可把 `train.py` 里的 `name="surface_crack"` 改成新名字（例如 `surface_crack2`）。

## 增量数据后再训

1. 新标注导出到 `data/yolo/labels/`
2. 运行整理脚本：

```bash
.\.venv\Scripts\python.exe src\organize_yolo_data.py
```

3. 再启动训练：

```bash
.\.venv\Scripts\python.exe src\train.py
```

## 常见问题

- **Windows 多进程报错**：训练代码必须在 `if __name__ == "__main__":` 内（当前脚本已包含）。
- **找不到图片 / 标签为空**：确认训练集在 `data/yolo/`，验证集在 `data/test/`，且路径与 `configs/data.yaml` 一致。
- **验证指标异常**：检查 `data/test/*.txt` 是否已写入多边形标注（空文件会被当成无目标）。
- **显存不足**：在 `model.train(...)` 中加 `batch=4` 或 `batch=2` 再试。
