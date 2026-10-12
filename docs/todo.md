# 待办计划

后续要做的事项记在这里。

---

## 清理 `data/train`（已完成，2026-10-12）

- [x] 删除目录 `data/train/`（约 640 张原始图库）
- [x] 删除 `src/organize_yolo_data.py` 与 `docs/organize_yolo_data.md`
- [x] 更新 `docs/train.md` 中关于 `data/train` 的说明

> 原始图片仍保留在 Label Studio 中；如需再次增量标注，请从 Label Studio 重新导出图片与标注，直接放入 `data/yolo/images/train` + `labels/train`。