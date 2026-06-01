# AGENTS.md

## Python 环境
- `python` NOT on PATH. Use full path:
  `"C:\Program Files\Anaconda3\python.exe"`
- Activate conda: `C:\Program Files\Anaconda3\Scripts\conda.exe activate`

## 运行与测试
- **启动**: `"C:\Program Files\Anaconda3\python.exe" app.py` → http://127.0.0.1:8050
- **预缓存 (必须)**: `"C:\Program Files\Anaconda3\python.exe" data_loader.py path/to/file.stdf.bz2`
  - 首次解析 ~38-44s/91MB (815 万记录), 缓存后 ~2.3s
  - COBVP 文件 ~5.4M 记录 → 25.1s
- **验证测试**: `"C:\Program Files\Anaconda3\python.exe" test_data_loader.py [path]`
  - 清缓存 → 重解析 → 校验 test 9207/9194 的 LSL/USL
  - 预期值硬编码为 G2TVP150AC 文件; 其他文件的 LSL/USL 可能不同 (如 COBVP 文件 9207 LO=7.03 而非 7.0)

## pystdf V4 解析 (v1.3.4)
- 模块 `pystdf`, Pipeline/Sink 模式, 非迭代器
- 用法: `Parser(V4.records, file_obj)`, `addSink(sink)`, `parse()`
- `before_send(self, source, data)`: `rec_type, fields = data`, 用 `isinstance` 判断类型
- 字段通过索引常量访问: `fields[V4.Ptr.RESULT]`
- 关键记录: `V4.Wir`, `V4.Pir`, `V4.Ptr`, `V4.Prr`, `V4.Ftr`
- BZ2 文件自动处理 (`bz2.open` if `.bz2`)

## 架构要点
- **缓存**: `./.stdf_cache/` Parquet (die + test 两表), key = MD5(绝对路径)
- **DuckDB**: `:memory:` 连接, SQL 聚合用于 Cpk (STDDEV_SAMP/POP), 非 pandas
- **状态共享**: `_data_cache["current"]` (模块全局) + `dcc.Store`: `selected-dies-store`, `highlight-bin-store`, `current-wafer-store`
- **着色模式**: `color-mode` radio → `"bin"` | `"test"`; 测试着色需要先选测试项
- **报告导出**: 两个 `dcc.Download`: 独立 HTML 和 PDF (WeasyPrint)

## 关键约定与陷阱
- **坐标单位**: mm (不是 wafer 坐标单位)
- **BIN 颜色**: `config.yaml` → `bin_colors`, key `1`=良品(绿), `other`=fallback gray
- **⚠ `bin_colors.pop("other")`** 在 `plots.create_wafer_map` (plots.py:27) 会**修改**全局 config dict. 如果 config 被重复传入, `other` key 会丢失.
- **⚠ V4 Cn 字段无 padding**: pystdf V4 的 Cn (TEST_TXT/ALARM_ID/UNITS/WIR wafer_id) 长度 = 1 + slen, **无** `(slen+1)&1` 对齐填充. V3/V4 行为不同, 自定义解析器必须区分.
- **新增图表**: `plots.py` 加函数 → `callbacks.py` 加回调 → `app.py` 加布局
- **新增记录类型**: 在 `data_loader.parse_stdf` 的 `before_send` 加 `isinstance` 分支
- **依赖变更**: 同步 `requirements.txt`
- **WeasyPrint PDF 在 Windows** 可能需 GTK 运行时; 失败时静默回退 (仅 HTML)
- **Cpk** 依赖 STDF 中的 LSL/USL 字段; 缺失时 `compute_cpk` 返回空 DataFrame
- **单晶圆视图**: 不支持多晶圆同时显示

## 项目结构
```
app.py              Dash 入口 + 布局
data_loader.py      STDF 解析 + Parquet 缓存 + DuckDB + CLI 预缓存入口
test_data_loader.py 独立测试脚本 (清缓存 → 解析 → 校验 LSL/USL)
plots.py            Plotly 图表 (wafer_map, scatter, pareto, cpk)
callbacks.py        Dash 交互回调 + config.yaml 加载
report_generator.py Jinja2 + WeasyPrint (HTML/PDF)
config.yaml         BIN 颜色, 晶圆 300mm, Cpk 阈值 1.33
templates/          report_template.html
assets/             style.css
```
