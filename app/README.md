# 桌面可视化应用

基于 **pywebview** 的 Web 套壳桌面界面，检测调用项目根目录 `best.pt`（与 `src/predict.py` 同权重、`conf=0.223`）。

## 启动

```bash
# 在项目根目录、本仓库虚拟环境中
.\.venv\Scripts\python.exe app\desktop.py
```

需已安装 `pywebview`、`ultralytics`，且根目录存在训练好的 `best.pt`。

也可直接用浏览器打开 `app/static/index.html` 预览界面布局（此时无法跑 YOLO）。

## 功能

- 导入单张图像或整个文件夹（JPEG / PNG / BMP / WebP）；支持拖放
- 单张检测当前预览图；批量检测仅处理勾选图像
- 预览叠加裂纹框与置信度；右下角图标可对比检测前后全貌
- 结果表展示（字段对齐接口规范）
- 左上角太阳 / 月亮切换白天与夜晚背景
- 导出前弹出命名窗口：`电池包裂纹_{产线}_{班次}_{日期}.csv`（日期滚轮，默认定位到当天）
