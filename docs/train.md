# YOLO 实例分割训练说明

用标注好的训练集训练表面裂纹分割模型。

## 数据划分

| 划分 | 路径 | 说明 |
| --- | --- | --- |
| train | `data/yolo/images/train` + `labels/train` | 已整理的训练样本 |
| val | `data/yolo/images/val` + `labels/val` | 验证集 |

配置见 `configs/data.yaml`。训练集整理步骤见 [organize_yolo_data.md](./organize_yolo_data.md)。

## 使用前

1. 训练集已整理到 `data/yolo/images|labels/train`
2. 验证集在 `data/yolo/images|labels/val`（含有效标注更佳）
3. 已安装依赖（虚拟环境中有 `ultralytics`）

## 开始训练

1. 打开 `src/train.py`，按需修改顶部配置：

| 项 | 默认 | 说明 |
| --- | --- | --- |
| `PRETRAINED` | `yolo26n-seg.pt` | 预训练分割模型（首次会自动下载到当前目录） |
| `EPOCHS` | `100` | 训练轮数 |
| `IMGSZ` | `640` | 输入尺寸 |
| `NAME` | `surface_crack` | 输出子目录名 |
| `EXIST_OK` | `True` | `True` 覆盖同名目录；`False` 则新建 `surface_crack-2` 等 |

2. 在项目根目录执行：

```bash
.\.venv\Scripts\python.exe src\train.py
```

有 GPU 时自动用 GPU，否则用 CPU。

## 结果在哪

```text
runs/segment/surface_crack/
  weights/
    best.pt    ← 验证集上最好的权重
    last.pt    ← 最后一轮权重
  results.csv / results.png
  *.jpg        ← 训练过程可视化
```

推理前请把 `best.pt` 复制到项目根目录（覆盖），供 [predict.md](./predict.md) 使用：

```bash
copy runs\segment\surface_crack\weights\best.pt best.pt
```

## 增量数据后再训

1. 新标注放到 `data/yolo/labels/`，对应原图在 `data/train/`
2. 运行整理：`.\.venv\Scripts\python.exe src\organize_yolo_data.py`
3. 再运行：`.\.venv\Scripts\python.exe src\train.py`
4. 再次把新的 `best.pt` 复制到项目根目录

## 常见问题

- **Windows 多进程报错**：须在 `if __name__ == "__main__":` 内启动（脚本已包含）。
- **找不到图片 / 标签为空**：核对 `data/yolo/` 与 `configs/data.yaml`。
- **验证指标异常**：检查 `data/yolo/labels/val/*.txt` 是否为有效多边形（空文件视为无目标）。
- **显存不足**：在 `train.py` 的 `model.train(...)` 中加 `batch=4` 或 `batch=2`。
