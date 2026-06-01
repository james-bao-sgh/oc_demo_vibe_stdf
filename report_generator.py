"""
Report generation module.
Produces HTML and PDF reports with Jinja2 templating and WeasyPrint.
"""

import base64
import logging
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
import numpy as np

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

_jinja_env = None


def _get_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    return _jinja_env


def _fig_to_base64(fig: go.Figure, width: int = 800, height: int = 500, scale: int = 2) -> str:
    try:
        img_bytes = fig.to_image(format="png", width=width, height=height, scale=scale)
        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to convert figure to image: {e}")
        return ""


def _safe_img(fig: go.Figure, width: int = 800, height: int = 500) -> str:
    b64 = _fig_to_base64(fig, width, height)
    if b64:
        return f"data:image/png;base64,{b64}"
    return ""


def generate_report(
    die_df: pd.DataFrame,
    test_df: pd.DataFrame,
    wafer_id: str,
    cpk_df: pd.DataFrame,
    wafer_map_fig: go.Figure,
    pareto_fig: go.Figure,
    cpk_fig: go.Figure,
    company_logo: Optional[str] = None,
) -> Dict[str, str]:
    total = len(die_df)
    if total == 0:
        return {"html": "", "pdf": ""}

    pass_count = len(die_df[die_df["hard_bin"] == 1])
    yield_rate = pass_count / total * 100 if total > 0 else 0.0

    bin_summary = die_df["hard_bin"].value_counts().reset_index()
    bin_summary.columns = ["bin", "count"]
    bin_summary["percentage"] = bin_summary["count"] / total * 100
    bin_summary = bin_summary.sort_values("count", ascending=False)

    top_fails = bin_summary[bin_summary["bin"] != 1].head(10)

    logo_b64 = ""
    if company_logo and os.path.exists(company_logo):
        with open(company_logo, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")

    cpk_rows = []
    if not cpk_df.empty:
        for _, r in cpk_df.iterrows():
            cpk_rows.append({
                "test_name": r["test_name"],
                "cpk": f"{r['cpk']:.3f}",
                "ppk": f"{r['ppk']:.3f}",
                "n": int(r["n"]),
                "mean": f"{r['mean']:.4f}",
                "lsl": f"{r['lsl']:.4f}",
                "usl": f"{r['usl']:.4f}",
                "abnormal": r["cpk"] < 1.33,
            })

    context = {
        "report_title": "STDF 晶圆测试报告",
        "wafer_id": wafer_id,
        "report_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_dies": total,
        "pass_count": pass_count,
        "fail_count": total - pass_count,
        "yield_rate": f"{yield_rate:.2f}",
        "bin_summary": bin_summary.to_dict("records"),
        "top_fails": top_fails.to_dict("records"),
        "cpk_data": cpk_rows,
        "wafer_map_img": _safe_img(wafer_map_fig, 800, 600),
        "pareto_img": _safe_img(pareto_fig, 700, 400),
        "cpk_img": _safe_img(cpk_fig, 700, 350),
        "logo_b64": logo_b64,
    }

    try:
        env = _get_env()
        template = env.get_template("report_template.html")
        html_content = template.render(**context)
    except Exception as e:
        logger.error(f"Template rendering failed: {e}")
        html_content = _fallback_html(context)

    report_path_html = REPORT_DIR / f"report_{wafer_id}_{datetime.now():%Y%m%d_%H%M%S}.html"
    report_path_html.write_text(html_content, encoding="utf-8")

    pdf_path = None
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
        pdf_path = REPORT_DIR / report_path_html.with_suffix(".pdf").name
        pdf_path.write_bytes(pdf_bytes)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    except Exception as e:
        logger.warning(f"PDF generation failed (WeasyPrint may be missing): {e}")
        pdf_b64 = ""

    return {
        "html": html_content,
        "html_path": str(report_path_html),
        "pdf_b64": pdf_b64,
    }


def _fallback_html(ctx: Dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{r['bin']}</td><td>{r['count']}</td><td>{r['percentage']:.1f}%</td></tr>"
        for r in ctx.get("bin_summary", [])
    )
    cpk_rows = "".join(
        f"<tr style='color:{'red' if r['abnormal'] else 'black'}'><td>{r['test_name']}</td>"
        f"<td>{r['cpk']}</td><td>{r['ppk']}</td><td>{r['n']}</td></tr>"
        for r in ctx.get("cpk_data", [])
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{ctx.get('report_title', 'Report')}</title></head>
<body>
<h1>{ctx['report_title']}</h1>
<h2>晶圆: {ctx['wafer_id']}</h2>
<p>日期: {ctx['report_date']}</p>
<h3>良率汇总</h3>
<p>总芯片: {ctx['total_dies']} | 良品: {ctx['pass_count']} | 不良: {ctx['fail_count']} | 良率: {ctx['yield_rate']}%</p>
<h3>BIN分布</h3>
<table border="1"><tr><th>BIN</th><th>数量</th><th>占比</th></tr>{rows}</table>
<h3>Cpk报告</h3>
<table border="1"><tr><th>测试项</th><th>Cpk</th><th>Ppk</th><th>N</th></tr>{cpk_rows}</table>
</body></html>"""
