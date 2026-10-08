# 标注数据整理说明

脚本：`src/organize_yolo_data.py`

用于把 Label Studio 导出的 YOLO 多边形标注整理进 Ultralytics **训练集**目录，并从 `data/train` 拉取对应图片。未标完全部图片也可以先整理、再训练。

验证集在 `data/yolo/images/val` + `labels/val`，本脚本不处理验证集。

## Label 导出后放哪里

### 训练集（本脚本处理）

1. 在 Label Studio 中按 **YOLO**（多边形 / 分割）格式导出标注。
2. 将导出得到的带 UUID 前缀的 `.txt` 文件放到：

```text
data/yolo/labels/
```

示例文件名：

```text
data/yolo/labels/c286dde2-image_172.txt
data/yolo/labels/94755ed9-image_173.txt
```

注意：

- 只放在 `data/yolo/labels/` **根目录**，不要直接丢进 `labels/train`。
- 文件名需包含原图 stem，形如 `{uuid}-image_数字.txt`。
- 对应原图需已存在于 `data/train/`（例如 `data/train/image_172.jpg`）。
- `classes.txt`、`notes.json` 可留在 `data/yolo/`，脚本不处理它们。

### 验证集（手动，不走本脚本）

按 YOLO 官方结构分别放置，例如：

```text
data/yolo/images/val/image_1.jpg
data/yolo/labels/val/image_1.txt
```

## 运行整理脚本

在项目根目录执行：

```bash
.\.venv\Scripts\python.exe src\organize_yolo_data.py
```

脚本会：

1. 识别 `data/yolo/labels/` 下的 `{uuid}-image_N.txt`
2. 在 `data/train/` 中查找 `image_N.jpg`
3. 去掉 UUID 前缀，写成 `image_N.txt`
4. 全部放入训练集
5. 复制图片与标注到 `data/yolo/images/train`、`data/yolo/labels/train`
6. 删除 `labels/` 根目录下已处理的 UUID 标注文件

## 整理后的目录结构

```text
data/
  train/                      ← 原始训练图片库（脚本只从这里拷图）
  yolo/
    images/train/             ← 训练图片
    images/val/               ← 验证图片
    labels/train/             ← 训练标签
    labels/val/               ← 验证标签
```

`configs/data.yaml`：`path` → `data/yolo`，`train` → `images/train`，`val` → `images/val`。

标注格式（YOLO segment 多边形，坐标归一化到 0~1）：

```text
0 x1 y1 x2 y2 ... xn yn
```

其中 `0` 对应类别 `Surface_Crack`。

## 增量标注流程

1. 继续在 Label Studio 标注新图片（训练集从 `data/train` 选图）
2. 导出 YOLO 标注，把新的 `{uuid}-image_N.txt` 放到 `data/yolo/labels/`
3. 再运行一次 `organize_yolo_data.py`
4. 运行训练：

```bash
.\.venv\Scripts\python.exe src\train.py
```

## 注意事项

- 每次运行只处理 `labels/` **根目录**里尚未整理的 UUID 文件；已在 `train/` 中的样本不会被重复处理。
- 原图目录 `data/train/` 不会被删除或移动，只做复制。
- 验证集请直接维护 `images/val` 与 `labels/val`，不要放到 `data/yolo/labels/` 根目录走本脚本。
