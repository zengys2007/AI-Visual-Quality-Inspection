# 赛题二：电池包表面裂纹检测 — YOLO26 可行路线

| 项 | 说明 |
| --- | --- |
| 赛题 | 绍兴市第一届大学生人工智能应用竞赛 · 智能制造与工业智能 AI 应用赛道 · 赛题二 |
| 检测目标 | 电池包表面裂纹 `Surface_Crack` |
| 检测框架 | Ultralytics YOLO26（本仓库已安装 `ultralytics==8.4.173`） |
| 输出契约 | `docs/接口规范.md`；与《附件1》CSV 八列完全一致 |
| 配套材料 | 可视化应用（必须）、项目方案、PPT、演示视频、源代码压缩包 |

本文按「能直接开工」写：先钉死数据与评分规则，再给模型、训练、后处理、应用、提交的分阶段路径。不依赖尚未实现的代码。

---

## 1. 目标与约束

### 1.1 必须同时做成的两件事

1. **算法**：在统一测试图像上检出裂纹实例，给出类别、像素框、置信度、单图耗时。
2. **工程**：可运行的可视化程序（导入图 / 跑检测 / 画框 / 保存 / 批量导出 CSV）。没有可运行应用 = 未完成本任务。

本科组算法性能占 **45%**（mAP50 / Precision / Recall 各 15%），应用开发 30%，创新 25%。专科组算法 30%、应用 45%。路线上应：**分割模型冲定位与召回，应用冲完整性和导出正确性，创新点写清楚且可演示。**

### 1.2 评分真正认什么

统一评测读的是 CSV，不是界面截图、不是 YOLO txt、不是 Mask。

表头必须一字不差：

```text
image_id,class_name,confidence,x_min,y_min,x_max,y_max,inference_time_ms
```

硬规则：

- `image_id` = 文件名含扩展名，与测试图逐字相同。
- 有裂纹：`class_name=Surface_Crack`，`confidence ∈ [0,1]` 保留两位小数，坐标为原图像素绝对值，且 `x_max>x_min`、`y_max>y_min`。
- 无检出：该图必须恰好一行 `Ok,-1,-1,-1,-1,-1,<真实耗时>`。禁止漏图。
- 一图多裂纹：多行同一 `image_id`，**各行 `inference_time_ms` 相同**（整图总耗时）。
- 分割 Mask / 多边形只作内部与可视化；CSV 填该实例的轴对齐外接矩形。
- 禁止窗帘布类别名（`Hole` / `Ink` / `Broken_Filament`），禁止 `crack`、`表面裂纹` 等非规定值。

### 1.3 赛题明确允许、且对本数据更合适的算法形态

附件 1 写明：电池包裂纹可采用实例分割，再把每个独立实例转为外接矩形。本数据集标注本身就是 **polygon**，不是宽高框。因此主路线定为：

**主模型：YOLO26 实例分割（`yolo26*-seg`）→ 实例 Mask/轮廓 → AABB → CSV。**

检测框模型（`yolo26*`）作为对照实验，用于验证「分割是否真的提升 mAP / Recall」。

---

## 2. 现有数据盘点（以本仓库实测为准）

图像分辨率统一 **640×480 JPEG**。类别仅一类：`Surface_Crack`。

| 目录 | 内容 | 实测规模 | 用途判断 |
| --- | --- | --- | --- |
| `data/测试集/` | jpg + 同名 json 多边形 + YOLO seg txt + `data.yaml` + 标注仓导出清单 | **160 张图、2073 个裂纹实例**；每张至少 1 条裂纹；每图实例数 1～24（中位数 13） | **唯一带实例标注的集合**，必须当作训练/验证源 |
| `data/训练集/` | 仅 jpg | **640 张**（`image_172.jpg`～`image_811.jpg` 连续） | **无实例标签**。更像主办方「不公开标签」的评测用图，或未标注扩充集 |
| `data/labels.xlsx` | `file_name` / 图像级标签 | 对应 160 张已标注图，全部为裂纹 | 图像级确认，不能替代多边形 |
| `data/瑕疵示意图/` | 裂纹示意 PNG | 5 张 | 方案/PPT 配图，不进训练 |

补充事实：

- `data/测试集/data.yaml` 已写 `nc: 1`、`names: ['Surface_Crack']`，但 `train:` / `val:` 仍是占位路径 `images/train`、`images/val`，**还不能直接拿去 `yolo train`**。
- txt 与 json 实例数一致，标注可直接当 YOLO-seg 格式用。
- 裂纹外接框偏小：面积 &lt;1024 的实例约 624/2073；宽或高 &lt;8px 约 45 个。细长裂纹用纯检测框容易框得过大或漏检。
- `image_180`～`image_185` 在两个目录都出现。划分与推理时按 **目录 + 文件名** 处理，避免覆盖。
- 160 张已标注图 **没有 OK 样本**。误检率指标会吃亏，必须靠阈值、NMS、可选的未标注图筛选来压假阳。

**数据使用原则（避免踩赛规）：**

1. 只用主办方发放的图、公开预训练权重、常规增强。禁止用任何方式反推「官方测试标签」，禁止人工改 CSV 刷分。
2. 文件夹名称与赛题用语不一致：名为「测试集」的目录带全量多边形。开发时 **不要把这 160 张的标签提交成官方成绩**；官方成绩应对 **无标签的那批图**（当前更像 `data/训练集/`，以现场最终下发目录为准）跑推理导出。
3. 若后续主办方另发无标签测试包，只替换推理输入目录，训练代码不动。

---

## 3. 总体技术路线

```text
标注多边形 (json/txt)
        │
        ▼
整理为 YOLO-seg 目录（train/val 8:2，固定随机种子）
        │
        ▼
裂纹增强预处理（LAB-CLAHE + 反锐化；可选黑帽融合）
  —— 训练 / 验证 / 正式推理必须走同一函数、同一参数
        │
        ▼
YOLO26-seg 微调（COCO 预训练）
        │
        ├─ 验证集：mask AP / box mAP50、P、R、漏检热图
        │
        ▼
推理：增强图进模型 → 实例 Mask → 外接矩形 → 置信度过滤 + NMS
        │
        ├─ 无框 → 写 Ok 占位行
        └─ 有框 → 每实例一行 Surface_Crack
        │
        ▼
可视化应用（原图叠加框，可切「增强预览」）+ UTF-8 CSV 导出
        │
        ▼
提交：源代码 + CSV + 方案 + PPT + 演示视频
```

创新点建议控制在「可实现、可写进方案」的 2～3 项，不要并行开太多：

1. **裂纹可见性预处理**：针对低对比涂覆面，把暗裂纹拉出来，再交给 YOLO26-seg（见第 6.4 节）。
2. **分割而非纯框**：贴合裂纹几何与附件 1 外接矩形规则。
3. **工业后处理**：按实例面积/细长度过滤噪声；置信度在验证集上扫一遍再锁死。
4. （可选）copy-paste / 伪标签——有余力再做，且必须「训推同一套预处理」。

---

## 4. 推荐工程目录（实现阶段按此建）

```text
AI-Visual-Quality-Inspection/
├── data/
│   ├── 测试集/                 # 现有标注源，不要改原文件
│   ├── 训练集/                 # 现有无标签图
│   └── yolo/                   # 整理后的训练数据（脚本生成）
│       ├── images/{train,val}/           # 建议直接存增强后图像
│       ├── images_raw/{train,val}/       # 可选：保留原图，便于对照实验
│       ├── labels/{train,val}/
│       └── battery_pack.yaml
├── configs/                    # 训练超参、预处理参数 yaml
├── models/                     # 下载的 yolo26s-seg.pt、训练产出 best.pt
├── src/
│   ├── data/                   # 划分、校验、统计
│   ├── preprocess.py           # 裂纹增强（唯一实现，训推共用）
│   ├── train.py                # 训练入口
│   ├── infer.py                # 单图/目录推理 → 内部结果结构
│   ├── export_csv.py           # 结果 → 附件1 CSV
│   └── app/                    # 可视化应用
├── outputs/
│   ├── runs/                   # ultralytics 训练日志
│   └── csv/
├── docs/
│   ├── 接口规范.md
│   └── YOLO26电池包检测可行路线.md   # 本文
└── requirements.txt
```

---

## 5. 阶段 0 — 环境（0.5 天）

当前虚拟环境已有 Ultralytics 8.4.x，默认配置即 YOLO26。补齐并冻结依赖即可。

```text
python -m pip install ultralytics opencv-python pillow pandas pyyaml
# 可视化二选一：PySide6（桌面，答辩投影更稳）或 Gradio/Streamlit（Web 快）
python -m pip install PySide6
```

GPU：有 CUDA 则 `device=0`；仅 CPU 也能训 `yolo26n-seg`，把 batch 降到 4～8，epochs 可缩短，精度会差一截。

预训练权重（训练时会自动下载，也可预拉）：

| 用途 | 权重 | 建议 |
| --- | --- | --- |
| 冒烟 | `yolo26n-seg.pt` | 先跑通数据与 CSV |
| **主提交** | `yolo26s-seg.pt` | 160 张数据下性价比最好 |
| 冲精度（GPU 够） | `yolo26m-seg.pt` | 注意过拟合，靠 val 早停 |
| 对照 | `yolo26s.pt`（detect） | 同一划分对比 mAP50 |

本机 cfg 中 YOLO26-seg 规模：n ≈ 3.1M / 10.5 GFLOPs，s ≈ 11.5M / 37.4 GFLOPs，m ≈ 27M / 132.5 GFLOPs。竞赛现场推理速度不是主评分项，但 CSV 要填真实耗时，应用里应用 `time.perf_counter()` 包住整图推理。

---

## 6. 阶段 1 — 数据整理与质检（0.5～1 天）

### 6.1 划分策略

仅用 `data/测试集` 的 160 张做有监督划分：

- **train : val = 8 : 2**（约 128 / 32），`seed=42` 写进脚本，保证可复现。
- 按「每图实例数」分层随机分，避免验证集全是简单图或全是 20+ 裂纹图。
- 图片复制或硬链接到 `data/yolo/images/{train,val}`，标签同步到 `data/yolo/labels/{train,val}`。
- **不要把 `data/训练集` 的 640 张混进有监督 train**（无标签会被当成负样本，若实际有裂纹会严重伤召回）。

`data/yolo/battery_pack.yaml` 示例：

```yaml
path: D:/Project/AI-Visual-Quality-Inspection/data/yolo
train: images/train
val: images/val
nc: 1
names:
  0: Surface_Crack
```

路径用正斜杠；`path` 写成绝对路径，避免 Windows 工作目录问题。

### 6.2 质检清单（脚本一次跑完）

- 每张 jpg 都有同名 txt；txt 每行：`class_id x1 y1 x2 y2 ...`（归一化多边形，class_id=0）。
- 坐标均在 `[0,1]`；点数 ≥ 3。
- 统计：实例数直方图、框宽高、空标签数（当前应为 0）。
- 抽 10 张把多边形画回原图，人工看是否贴裂纹，而不是整包外壳。
- 记录与 `data/训练集` 重名的 6 张（180～185），训练只用「测试集」目录里的那份标注。

### 6.3 已知风险与对策

| 风险 | 对策 |
| --- | --- |
| 无 OK 标注，模型倾向每图都报裂纹 | val 上提高 `conf`；导出前过滤极小框；应用里展示 OK/NG |
| 一图十几条裂纹，NMS 过猛会吞实例 | `max_det` 设 50～100（标注最大 24）；`iou` 不要过高（建议 0.5～0.65） |
| 细长裂纹 box IoU 对不准 | 主攻 seg；评测虽看框，但框由 Mask 外接得到，通常更贴目标 |
| 160 张易过拟合 | 早停、不强上 x 模型、末期关 mosaic、固定 val 不拿来调到死 |

### 6.4 裂纹可见性预处理（建议做，且必须训推一致）

实拍是灰蓝涂覆面 + JPEG 压缩噪声，裂纹是**比背景更暗的细线**。浅裂纹（如 `image_100.jpg`）肉眼都费劲，YOLO 直接吃原图会偏漏检。赛题也点名可用颜色空间、边缘、形态学等传统视觉，和深度学习拼在一起是合理创新点。

**先钉三条硬约束，再选算法：**

1. **几何不变**：不裁剪、不缩放、不旋转、不仿射。输出与输入同为 640×480，多边形标签可原样复用，CSV 坐标仍是原图像素。
2. **训推同一函数**：`enhance(img)` 只实现一次。训练存增强图或推理在线增强，参数锁死在 `configs/preprocess.yaml`。只增强训练集、测试走原图 = 分布错位，往往比不增强更差。
3. **耗时算进检测**：`inference_time_ms` 从读图后的增强开始计，到得到框为止。

#### 推荐主配方（先上这个）

目标：压光照不均、抬局部对比、让暗裂纹变「黑」、略锐化，但不要把涂层纹理锐成假裂纹。

```text
BGR 原图
  → 转 LAB，只对 L 做 CLAHE（clipLimit≈2.0，tile=8×8）
  → 回到 BGR
  → 反锐化（Unsharp：高斯模糊核 0，强度 1.2～1.5）
  → uint8 输出，与原图同尺寸
```

示意（OpenCV，参数写入配置文件，禁止散落魔法数）：

```python
import cv2
import numpy as np

def enhance_crack(bgr, clip_limit=2.0, tile=8, sharp=1.35):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile, tile))
    l = clahe.apply(l)
    out = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(out, (0, 0), 3)
    return cv2.addWeighted(out, sharp, blur, 1.0 - sharp, 0)
```

为什么选这套：裂纹是暗线，对比度差在亮度不在色相；CLAHE 在 L 通道比 RGB 直方图均衡更稳，也不把 a/b 通道拉花。反锐化补 JPEG 发糊，不引入新边缘算子阈值。

#### 可选加强（主配方 val 仍漏浅纹时再加）

暗裂纹可用 **黑帽（black-hat）**：`blackhat = close(gray) - gray`，再按权重叠回：

```text
gray → 形态学闭运算（椭圆核 15～21）→ blackhat
增强图 = saturate(CLAHE图 - α * blackhat)   # α 约 0.8～1.5
```

黑帽会把细暗缝「掏」出来，也会放大接缝和脏点。α 过大假阳会升。加这项必须做对照：主配方 vs 主配方+黑帽，看 val 的 Recall 和 Precision。

**明确后置、不要一上来就堆的：**

| 方法 | 对本数据的风险 |
| --- | --- |
| Canny / Sobel 当模型输入 | 二值边缘丢纹理，COCO 预训练 RGB 统计被破坏 |
| 全局直方图均衡 | 一块亮斑会压掉整图裂纹 |
| Retinex / 重双边滤波 | 慢，且易把涂层颗粒当成裂纹 |
| 超分 / 把图放大再训 | 坐标映射容易错，且原图已是 640 |
| 只对裂纹 ROI 增强 | 测试时没有 GT，用不了 |

#### 接入训练的两种做法

| 方式 | 做法 | 适用 |
| --- | --- | --- |
| **离线烘焙（推荐）** | 划分后对 `images/train`、`images/val` 跑同一 `enhance_crack`，覆盖或写入新目录；标签不动 | 实现简单、训练时无额外 CPU、可复现 |
| 在线回调 | Ultralytics 自定义 augment 里先 enhance 再 mosaic | 想和随机增强搅在一起时再用，调试成本高 |

对照实验（同一划分、同一超参）：

1. 原图 baseline  
2. LAB-CLAHE + 反锐化（主提交候选）  
3. 仅当 2 的 Recall 不够时：+ 黑帽  

看 **Box mAP50 / P / R**，以及增强前后并排图（方案和 PPT 必备）。应用里建议：检测走增强图，画框叠在**原图**上，另提供「增强预览」开关，避免评委觉得图被「PS 过」。

#### 和 YOLO 随机增强的关系

预处理已经拉过对比度后，训练里的 `hsv_v` / `hsv_s` 建议略降（例如 `hsv_v=0.3`、`hsv_s=0.4`），避免把刚抬出来的裂纹又洗掉。`mosaic`、`copy_paste`、翻转仍加在增强图上，没有冲突。

#### 落地检查

- 抽 8～10 张（含浅裂纹如 `image_100`、深裂纹如 `image_50`）做原图 | 增强 | 标注叠加三联图，确认裂纹更黑、涂层没有布满假纹。
- `np.array_equal(raw.shape, enh.shape)` 必须为真。
- 推理路径：`bgr = cv2.imread(...)` → `enh = enhance_crack(bgr)` → `model.predict(enh)`；框画回 `bgr`。

---

## 7. 阶段 2 — 训练（1～2 天，含一次对照）

### 7.1 冒烟（确认数据格式）

```python
from ultralytics import YOLO

model = YOLO("yolo26n-seg.pt")
model.train(
    data="data/yolo/battery_pack.yaml",
    epochs=5,
    imgsz=640,
    batch=8,
    device=0,          # 无 GPU 改为 "cpu"
    project="outputs/runs",
    name="smoke_n_seg",
    exist_ok=True,
)
```

成功标志：能出 `results.png`、val 能算出 box/mask 指标，无「label empty / cache mismatch」。

### 7.2 主训练建议超参

原图已是 640 宽，`imgsz=640` 足够；裂纹小则保持 640，不要降到 320。

```python
from ultralytics import YOLO

model = YOLO("yolo26s-seg.pt")
model.train(
    data="data/yolo/battery_pack.yaml",
    epochs=150,
    patience=40,
    imgsz=640,
    batch=16,              # 显存不够改为 8
    device=0,
    workers=4,
    seed=42,
    deterministic=True,
    optimizer="auto",
    lr0=0.01,
    close_mosaic=15,
    hsv_h=0.01,            # 已做 CLAHE 时不要再猛拉色彩
    hsv_s=0.4,
    hsv_v=0.3,
    degrees=10,            # 裂纹方向不固定，轻度旋转
    translate=0.1,
    scale=0.5,
    flipud=0.0,            # 工业相机多正装，先关上下翻转
    fliplr=0.5,
    mosaic=1.0,
    mixup=0.0,             # 小目标上 mixup 常伤定位
    copy_paste=0.3,        # 分割任务有效，可从 0.1 试到 0.5
    overlap_mask=True,
    mask_ratio=4,
    max_det=100,
    project="outputs/runs",
    name="yolo26s_seg_main",
)
```

权重取 `outputs/runs/yolo26s_seg_main/weights/best.pt`（按 val 指标），同时保留 `last.pt`。

### 7.3 对照与加码顺序（不要一次全开）

1. 原图 `yolo26s-seg`（baseline）。
2. **同一划分**上的 CLAHE+反锐化 `yolo26s-seg`（主路径）。
3. 同划分 `yolo26s` detect：验证分割是否真提升 box 指标。
4. 若增强后 Recall 仍不够：再试 +黑帽；若欠拟合再试 `yolo26m-seg`。
5. 过拟合则减 epochs / copy_paste，不要靠继续加重预处理硬抬训练损失。

### 7.4 验证时看哪些数

Ultralytics seg 会同时报 mask 与 box。**赛题 mAP50 / P / R 按框评**，所以：

- 主看 **Box mAP50、Box Precision、Box Recall**。
- Mask 指标用于判断分割是否学到裂纹形状。
- 导出 val 预测图：检查漏检细纹、把接缝/反光当成裂纹的假阳。
- `max_det` 是否截断：验证集单图预测数若经常顶到上限，再加大。

在 val 上扫 `conf ∈ {0.15, 0.20, 0.25, 0.30, 0.40}`，锁定一组 **F1 或 Recall 优先** 的阈值写入应用配置。裂纹漏检通常比多报一个框更伤 Recall；但误检率也在赛题表里，OK 图（无标签的 640 张里可能存在）不能刷屏。建议先保 Recall，再用最小外接面积去掉明显噪点。

---

## 8. 阶段 3 — 推理与 CSV（0.5～1 天）

这是整条链路里最容易「模型还行、提交零分」的地方，必须单独测。

### 8.1 单图推理逻辑（伪代码）

```text
t0 = perf_counter()
enhanced = enhance_crack(image)          # 与训练完全相同的参数
result = model.predict(enhanced, conf=CONF, iou=0.55, max_det=100, retina_masks=True, verbose=False)[0]
elapsed_ms = (perf_counter() - t0) * 1000   # 含预处理
# 可视化把框画回 image（原图），不要只展示增强图

rows = []
if result.masks is not None and len(result.masks) > 0:
    for i in range(len(result.masks)):
        # 优先用 mask 非零像素的 min/max；否则用多边形点
        x_min, y_min, x_max, y_max = aabb_from_mask(result.masks.data[i], orig_shape)
        conf = round(float(result.boxes.conf[i]), 2)
        if (x_max - x_min) < 2 or (y_max - y_min) < 2:
            continue
        # 裁剪到图像范围内
        rows.append(Surface_Crack, conf, x_min, y_min, x_max, y_max)
if not rows:
    rows.append(Ok, -1, -1, -1, -1, -1)

每一行都带同一 elapsed_ms
image_id = 原始文件名（含 .jpg）
```

注意：

- 坐标必须相对 **原始 640×480**，不要用 letterbox 后的张量坐标。Ultralytics `result.boxes.xyxy` 一般已是原图像素；Mask 要用官方映射或 `result.masks.xy` 轮廓点取 min/max。
- `confidence` 先 `float` 再 `round(..., 2)`。
- 批量时逐张计时，不要把整目录总时间均分（评测可能看均值，但规则要求单图真实总耗时）。
- 未检出必须写 `Ok`，哪怕你「觉得这张肯定有裂纹」。

### 8.2 自测 CSV

对 val 的 32 张导出一份 CSV，检查：

- 表头 8 列、UTF-8、逗号分隔。
- 图数 = 32，无漏文件。
- 类别只有 `Surface_Crack` 或 `Ok`。
- 用 val 的 txt 多边形生成 GT 框，本地算一遍 mAP50 / P / R，与训练日志对照，确认导出没有把 xywh 当成 xyxy、没有把归一化坐标写出。

再用 `data/训练集` 全量 640 张跑批量导出，得到提交用 `团队名称_检测结果.csv`（团队名用昵称，见第 12 节）。抽查：重名图、空预测比例、单图行数是否离谱（例如 100 条几乎肯定阈值过低）。

---

## 9. 阶段 4 — 可视化应用（1～2 天，与推理并行）

赛题硬性要求。建议 **PySide6 桌面应用**（答辩投屏不依赖浏览器端口）。功能最小闭环：

| 功能 | 说明 |
| --- | --- |
| 打开图像 | jpg/png/bmp |
| 打开文件夹 | 扫描常见图像后缀，不漏图 |
| 单张检测 | 叠加外接框 + 类别 + 置信度；可选半透明 Mask |
| 批量检测 | 进度条；完成后列表可点选回看 |
| 图像级 OK/NG | 有 `Surface_Crack` 为 NG，否则 OK |
| 保存可视化图 | 带框 PNG |
| 导出 CSV | 默认文件名 `团队名称_检测结果.csv`，编码 UTF-8 |
| 状态栏 | 当前模型路径、conf、单图耗时、已处理张数 |

工程规范性（占应用分）：

- 模型路径可配置，缺权重时给出明确中文错误，而不是崩溃。
- 推理放到工作线程，避免界面卡死。
- 日志：开始/结束、失败文件名。
- 不出现学校、专业、导师信息（文件名、窗口标题、关于页都不要）。

用户体验：默认 conf 用验证集锁定值；提供滑条但导出时用「当前设置」并在方案里写死推荐值。

---

## 10. 阶段 5 — 指标、误差分析与方案写作（1 天）

方案（Word+PDF，≤30 页，宋体小四）建议结构：

1. 研究现状与意义（电池包裂纹、工业质检、YOLO 系列到 YOLO26）。
2. 目标与思路（分割→外接框→CSV；为什么不用纯分类）。
3. 数据理解（160 标注 / 2073 实例 / 小目标统计 / 无 OK 标注的影响）。
4. 算法设计（YOLO26-seg、增强、后处理、阈值）。
5. 实现（目录、训练命令、应用架构）。
6. 结果：val 上 mAP50 / P / R 表；与 detect 对照；典型 TP/FP/FN 图（用 `data/瑕疵示意图` 风格解读）。
7. 创新与实用性（产线节拍、可复现、导出规范）。
8. 团队昵称与分工（不要真实校名）。

答辩 PPT ≤20 页：问题 → 数据 → 结构图 → 指标 → 应用截图/GIF → 分工。

演示视频 ≤10 分钟 MP4：数据划分一笔带过 → 训练曲线 → 应用从导入到导出 CSV 的完整操作 → 打开 CSV 给评委看表头。

---

## 11. 建议排期（可压缩到约一周）

| 天数 | 产出 |
| --- | --- |
| D1 | 环境、数据划分、裂纹增强三联图抽检、离线烘焙增强集、n-seg 冒烟 |
| D2 | 原图 vs 增强 的 s-seg 对照 + val 阈值扫描 |
| D3 | 推理/CSV 管道 + 对 640 张无标签图试跑；detect 对照（可选） |
| D4 | 桌面应用闭环：单张、批量、导出 |
| D5 | 误差分析、微调一轮（copy_paste / conf / 面积过滤） |
| D6 | 方案、PPT、演示视频、打包自检 |

GPU 弱则 D2 用 n/s、减 epochs，优先保证 **应用 + 合法 CSV**。

---

## 12. 提交包（按《竞赛提交要求》）

最高层目录用 **团队昵称**，再打成 `团队名称.rar`。单队源码压缩包 ≤500MB。

| 材料 | 命名 | 注意 |
| --- | --- | --- |
| 工程源码 + CSV | `团队名称_源代码`（压缩包内） | 不要塞 `.venv`、原始上万张中间结果；权重 `best.pt` 可保留一份 |
| 检测结果 CSV | `团队名称_检测结果.csv` | 对官方测试图（当前按无标签 640 张或现场指定目录） |
| 方案 | `团队名称_项目方案`.docx/.pdf | 各一份、内容相同 |
| PPT | `团队名称_项目介绍 PPT` | ≤100MB |
| 视频 | `团队名称_演示视频`.mp4 | ≤200MB、≤10 分钟 |

全文、视频、**目录名** 均不得出现学校、专业、指导教师姓名或暗示。

---

## 13. 提交前总检

算法与 CSV：

- [ ] 训练用的是多边形 YOLO-seg，类别名 `Surface_Crack`
- [ ] 预处理几何不变；训练/验证/提交推理调用同一 `enhance_crack` 与同一组参数
- [ ] `inference_time_ms` 包含预处理时间；框画在原图坐标系
- [ ] 导出框来自 Mask/轮廓外接矩形，像素绝对值
- [ ] 每张测试图至少一行；无漏检图；无「有裂纹还写 Ok」混排
- [ ] 同图多行耗时一致；confidence 两位小数
- [ ] 本地 val mAP50 / P / R 已记录进方案

应用：

- [ ] 导入、检测、可视化、保存、批量导出均可现场操作
- [ ] 窗口标题/关于页无违规信息

打包：

- [ ] 不含 `.venv`、不含赛题保密标签的二次分发说明争议文件（原 `data/测试集` 标注是主办方发放的训练材料，可随源码；**不要声称那就是官方测试答案**）
- [ ] 压缩包能在干净环境按 README 安装并打开应用

---

## 14. 明确不做什么（保证可行）

- 不上双阶段检测器堆砌、不上未验证的自研骨干。
- 不把 640 张无标签图当有监督正负样本直接训练。
- 不人工逐张改 CSV。
- 不在应用里做「导出前按文件名查表填框」。
- 创新不写空话；每一条都能在视频里点出来。

按本文顺序做完，即可得到一条可训练、可验证、可演示、可提交的 YOLO26 电池包裂纹检测工程。
