"""整理 Label Studio 导出的标注，并复制对应图片到 data/yolo。"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

# ── 配置（路径相对项目根目录）─────────────────────────
# 输入：Label Studio 导出的 .txt 放在 labels 根目录；原图从 data/train 拉取
# 验证集在 data/yolo/images/val + labels/val，本脚本不处理
SRC_LABELS = Path("data/yolo/labels")
IMG_DIRS = [Path("data/train")]

# 输出：整理后的训练集
OUT_IMG_TRAIN = Path("data/yolo/images/train")
OUT_LBL_TRAIN = Path("data/yolo/labels/train")
# ─────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
UUID_LABEL = re.compile(r"^[0-9a-fA-F]+-(image_\d+)\.txt$")


def main() -> None:
    os.chdir(ROOT)

    for d in (OUT_IMG_TRAIN, OUT_LBL_TRAIN):
        d.mkdir(parents=True, exist_ok=True)

    items: list[tuple[str, Path, Path]] = []
    for p in sorted(SRC_LABELS.glob("*.txt")):
        m = UUID_LABEL.match(p.name)
        if not m:
            print(f"skip unexpected label: {p.name}")
            continue
        stem = m.group(1)
        src_img = next((d / f"{stem}.jpg" for d in IMG_DIRS if (d / f"{stem}.jpg").exists()), None)
        if src_img is None:
            print(f"MISSING image for {p.name}")
            continue
        items.append((stem, p, src_img))

    print(f"matched pairs: {len(items)}")
    if not items:
        raise SystemExit("no labeled images to organize")

    moved_src: list[Path] = []
    for stem, lbl, img in items:
        out_img = OUT_IMG_TRAIN / f"{stem}.jpg"
        out_lbl = OUT_LBL_TRAIN / f"{stem}.txt"
        shutil.copy2(img, out_img)
        shutil.copy2(lbl, out_lbl)
        moved_src.append(lbl)
        print(f"[train] {stem}.jpg + {stem}.txt")

    for p in moved_src:
        p.unlink()
        print(f"removed {p.name}")

    gk = OUT_IMG_TRAIN / ".gitkeep"
    if gk.exists() and any(x.name != ".gitkeep" for x in OUT_IMG_TRAIN.iterdir()):
        gk.unlink()
    gk = OUT_LBL_TRAIN / ".gitkeep"
    if gk.exists() and any(x.name != ".gitkeep" for x in OUT_LBL_TRAIN.iterdir()):
        gk.unlink()

    print("--- summary ---")
    print("images/train", len(list(OUT_IMG_TRAIN.glob("*.jpg"))))
    print("labels/train", len(list(OUT_LBL_TRAIN.glob("*.txt"))))
    leftover = list(SRC_LABELS.glob("*.txt"))
    print("leftover root labels", [p.name for p in leftover])


if __name__ == "__main__":
    main()
