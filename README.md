# STDF Wafer Data Analyzer

基于 Plotly Dash 的 STDF 晶圆测试数据分析 Web 工具。

## 功能

- **文件加载**: 输入 STDF 文件路径，自动解析并缓存为 Parquet；首次加载较慢（~10min/60MB），**建议先 CLI 预缓存**
- **晶圆图**: BIN 着色 / 测试值渐变着色，点击芯片联动高亮同 BIN 芯片
- **散点图**: 测试项结果分布，点击联动晶圆图
- **BIN Pareto**: 柱状图 + 累计百分比，点击筛选失效聚类
- **Cpk/Ppk**: 自动计算，异常项（Cpk < 1.33）红色高亮
- **追踪面板**: 单芯片全部参数、多芯片统计摘要
- **报告导出**: HTML + PDF（WeasyPrint），含良率、Pareto、Cpk、晶圆图

## 安装

```bash
"C:\Program Files\Anaconda3\python.exe" -m pip install -r requirements.txt
```

> **注意**: `python` 不在 PATH 中（Microsoft Store 别名冲突），请使用完整路径。

## 预缓存（重要）

首次加载 STDF 极慢（~10 分钟），建议先 CLI 预缓存：

```bash
"C:\Program Files\Anaconda3\python.exe" data_loader.py path/to/file.stdf.bz2
```

预缓存后，Web 界面加载只需 ~10 秒。

## 运行

```bash
"C:\Program Files\Anaconda3\python.exe" app.py
```

浏览器访问 `http://127.0.0.1:8050`。

## 配置

编辑 `config.yaml`，例如修改 BIN 颜色映射或 Cpk 阈值。

## 项目结构

```
├── app.py                  # Dash 主入口
├── data_loader.py          # STDF 解析 + Parquet 缓存 + DuckDB + CLI 预缓存
├── plots.py                # Plotly 图表构建
├── callbacks.py            # Dash 交互回调
├── report_generator.py     # Jinja2 + WeasyPrint 报告
├── config.yaml             # BIN 颜色、晶圆参数
├── requirements.txt
├── templates/
│   └── report_template.html
└── assets/
    └── style.css
```
