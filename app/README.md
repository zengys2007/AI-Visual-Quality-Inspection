# 桌面可视化应用（Mock UI）

基于 **pywebview** 的 Web 套壳桌面界面，用于演示赛题要求的导入 / 检测 / 可视化 / 导出流程。

当前检测为前端 Mock，不调用 YOLO 权重。

## 启动

```bash
# 在项目根目录、已激活的虚拟环境中
pip install pywebview
python app/desktop.py
```

也可直接用浏览器打开 `app/static/index.html` 预览界面。

## 功能

- 导入单张图像或整个文件夹（JPEG / PNG / BMP / WebP）
- 单张 / 批量 Mock 检测，预览叠加框与置信度
- 结果表展示（字段对齐接口规范）
- 导出 `视觉检测团队_检测结果.csv`
