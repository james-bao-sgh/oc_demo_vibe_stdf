# Open Points List
[TOC]

## 2026-06-01 散点图缩放交互增强

- **对应模块**：scatter plot
- **功能**：散点图鼠标框选缩放 / 平移
- **现状**：`clickmode="event+select"` + `displayModeBar: False` 导致鼠标拖拽被框选模式劫持，无法拖拽缩放。
- **方案**：
  - `plots.py`: `clickmode="event+select"` → `clickmode="event"` + 增加 `dragmode="zoom"`
  - `app.py`: 显示模式栏 (zoom2d/pan2d/resetScale2d/autoScale2d)，隐藏 logo
- **示意图**：TBD — 后续使用 plot 生成的 PNG
- **预期交互**：
  - 框选放大：鼠标拖拽矩形
  - 平移：模式栏切 pan 模式后拖拽
  - 恢复全图：双击 或 点 reset
  - 选芯片：单击数据点（保留）
- **影响**：芯片选择正常，view_mode 切换时 y 轴自动重置，缩放互不影响
- **状态**：待确认是否执行
