# 待办计划

后续要做的事项记在这里。

---

## 清理 `data/train`

### 现状

- `data/train/`：原始训练图片库（约 640 张），**训练/验证/预测不直接使用**。
- 仍被 `src/organize_yolo_data.py` 的 `IMG_DIRS` 引用：整理 Label Studio 导出标注时，从这里拷图到 `data/yolo/images/train`。

### 可执行前提（全部满足后再做）

- [ ] 后续不再从 Label Studio 导出新标注到 `data/yolo/labels/` 根目录做整理
- [ ] 或已改写 `organize_yolo_data.py`，不再依赖 `data/train`（例如改为从别的原图目录取图）
- [ ] 确认所需训练图已在 `data/yolo/images/train`，不需要再从 `data/train` 补拷

### 执行时一并改

- [ ] 删除目录 `data/train/`
- [ ] 更新 `src/organize_yolo_data.py`（去掉或替换 `IMG_DIRS`）
- [ ] 更新 `docs/organize_yolo_data.md`、`docs/train.md` 中关于 `data/train` 的说明
