"""整理 Label Studio 导出的标注，并复制对应图片到 data/yolo。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
YOLO = DATA / "yolo"
SRC_LABELS = YOLO / "labels"
# 训练集原图只从 data/train 拉取；data/test 作为验证集，不并入 train
IMG_DIRS = [DATA / "train"]

OUT_IMG_TRAIN = YOLO / "images" / "train"
OUT_LBL_TRAIN = YOLO / "labels" / "train"

UUID_LABEL = re.compile(r"^[0-9a-fA-F]+-(image_\d+)\.txt$")


def main() -> None:
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
