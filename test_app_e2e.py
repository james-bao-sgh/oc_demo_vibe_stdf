"""
End-to-end test for STDF Analyzer.

Loads sample data via parse_stdf, then verifies all chart
functions produce correct outputs with the right number of traces,
shapes, and axis ranges for each scatter view mode.
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from data_loader import parse_stdf
import plots

SAMPLE_FILE = str(
    Path(__file__).parent
    / "G2TVP150AC_8_5012114_09_5034758_MP3_TEMP_140_DEG_20250429_084931.std_20250616T195442000.bz2"
)

EXPECTED_DIES = 3289
EXPECTED_TEST_ITEMS = 3436
FIRST_TEST = "P9194_K7_VTH_AS1A0AFTERTRIM"


def run_tests():
    passed = 0
    failed = 0

    def check(name, ok, detail=""):
        nonlocal passed, failed
        if ok:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} — {detail}")
            failed += 1

    # ── 0. Load data ──
    print("\n--- 0. Load STDF file ---")
    t0 = time.time()
    data = parse_stdf(SAMPLE_FILE)
    load_time = time.time() - t0
    check("Data loaded", data["total_dies"] > 0, f"dies={data['total_dies']}")
    print(f"       {data['total_dies']} dies, {len(data['test_items'])} tests in {load_time:.1f}s")
    check("Die count", data["total_dies"] == EXPECTED_DIES,
          f"got {data['total_dies']}, expected {EXPECTED_DIES}")
    check("Test items count", len(data["test_items"]) == EXPECTED_TEST_ITEMS,
          f"got {len(data['test_items'])}, expected {EXPECTED_TEST_ITEMS}")

    die_df = data["die_info"]
    test_df = data["test_results"]

    # ── 1. Wafer map (bin mode) ──
    print("\n--- 1. Wafer map (bin mode) ---")
    fig = plots.create_wafer_map(die_df, test_df, color_mode="bin")
    check("Bin map 1+ traces", len(fig.data) >= 1, f"got {len(fig.data)}")

    # ── 2. Wafer map (test mode) ──
    print("\n--- 2. Wafer map (test mode) ---")
    fig = plots.create_wafer_map(die_df, test_df, color_mode="test", test_name=FIRST_TEST)
    check("Test map has traces", len(fig.data) >= 1, f"got {len(fig.data)}")

    # ── 3. Scatter — normal mode (with LSL/USL y-range) ──
    print("\n--- 3. Scatter plot (normal mode) ---")
    fig = plots.create_scatter_plot(die_df, test_df, FIRST_TEST, view_mode="normal")
    check("Normal mode 1+ traces", len(fig.data) >= 1, f"got {len(fig.data)}")

    # Normal: y-range from LSL/USL with 20% margin
    yaxis = fig.layout.yaxis
    yrange = None
    if yaxis and hasattr(yaxis, 'range') and yaxis.range:
        yrange = yaxis.range
    expected_lo = 3.85 - (4.15 - 3.85) * 0.2
    expected_hi = 4.15 + (4.15 - 3.85) * 0.2
    if yrange:
        check(f"Normal y-range [{yrange[0]:.2f}, {yrange[1]:.2f}]",
              abs(yrange[0] - expected_lo) < 0.05 and abs(yrange[1] - expected_hi) < 0.05,
              f"expected [{expected_lo:.3f}, {expected_hi:.3f}]")
    else:
        check("Normal y-axis range set", False, "no range in yaxis")

    shapes = fig.layout.shapes or ()
    hlines = [s for s in shapes if getattr(s, 'type', None) == 'line' or s.get('type') == 'line']
    check("Normal has LSL/USL hlines", len(hlines) >= 2, f"got {len(hlines)} lines")

    # ── 4. Scatter — minmax mode ──
    print("\n--- 4. Scatter plot (minmax mode) ---")
    fig = plots.create_scatter_plot(die_df, test_df, FIRST_TEST, view_mode="minmax")
    shapes = fig.layout.shapes or ()
    hlines = [s for s in shapes if getattr(s, 'type', None) == 'line' or (isinstance(s, dict) and s.get('type') == 'line')]
    check("Minmax has min/max lines",
          len(hlines) >= 4,  # LSL + USL + Min + Max
          f"got {len(hlines)} lines")

    yaxis = fig.layout.yaxis
    yrange = None
    if yaxis and hasattr(yaxis, 'range') and yaxis.range:
        yrange = yaxis.range
    if yrange:
        # Minmax: y-range from data min/max with 20% margin
        subset = test_df[test_df["test_name"] == FIRST_TEST]
        data_min = subset["result"].min()
        data_max = subset["result"].max()
        data_rng = data_max - data_min
        exp_lo = data_min - data_rng * 0.2
        exp_hi = data_max + data_rng * 0.2
        check(f"Minmax y-range [{yrange[0]:.3f}, {yrange[1]:.3f}]",
              abs(yrange[0] - exp_lo) < 0.1 and abs(yrange[1] - exp_hi) < 0.1,
              f"expected [{exp_lo:.3f}, {exp_hi:.3f}]")

    # ── 5. Scatter — bin1 mode ──
    print("\n--- 5. Scatter plot (bin1 mode) ---")
    fig = plots.create_scatter_plot(die_df, test_df, FIRST_TEST, view_mode="bin1")
    check("Bin1 mode renders", len(fig.data) >= 1, f"got {len(fig.data)}")
    yaxis = fig.layout.yaxis
    yrange = None
    if yaxis and hasattr(yaxis, 'range') and yaxis.range:
        yrange = yaxis.range
    exp_lo = 3.85 - (4.15 - 3.85) * 0.05
    exp_hi = 4.15 + (4.15 - 3.85) * 0.05
    if yrange:
        check(f"Bin1 y-range [{yrange[0]:.3f}, {yrange[1]:.3f}]",
              abs(yrange[0] - exp_lo) < 0.02 and abs(yrange[1] - exp_hi) < 0.02,
              f"expected [{exp_lo:.3f}, {exp_hi:.3f}]")

    # ── 6. Pareto chart ──
    print("\n--- 6. Pareto chart ---")
    fig = plots.create_pareto_chart(die_df)
    check("Pareto bar+line", len(fig.data) == 2, f"got {len(fig.data)}")

    # ── 7. Cpk cards ──
    print("\n--- 7. Cpk computation ---")
    from data_loader import compute_cpk
    cpk_df = compute_cpk(test_df)
    check("Cpk returns data", not cpk_df.empty, f"rows={len(cpk_df)}")
    if not cpk_df.empty:
        check("Cpk has expected columns",
              all(c in cpk_df.columns for c in ["cpk", "ppk", "lsl", "usl"]),
              f"columns={list(cpk_df.columns)}")
        fig = plots.create_cpk_cards(cpk_df)
        check("Cpk chart has traces", len(fig.data) > 0, f"got {len(fig.data)}")

    # ── 8. Die selection table ──
    print("\n--- 8. Die selection table ---")
    fig = plots.create_test_item_table(die_df, test_df, selected_dies=[1])
    check("Selected die table renders", len(fig.data) >= 1, f"got {len(fig.data)}")

    # ── 9. Verify test limits (data quality) ──
    print("\n--- 9. Data quality: test limits ---")
    for tn, exp_lo, exp_hi in [(9207, 7.0, 7.65), (9194, 3.85, 4.15)]:
        subset = test_df[test_df["test_num"] == tn]
        lo = subset["low_limit"].dropna().unique()
        hi = subset["high_limit"].dropna().unique()
        if len(lo) == 0 or len(hi) == 0:
            check(f"Test {tn} limits found", False, "not found")
        else:
            ok_lo = abs(lo[0] - exp_lo) < 0.001
            ok_hi = abs(hi[0] - exp_hi) < 0.001
            check(f"Test {tn} LO={lo[0]:.3f}", ok_lo,
                  f"expected {exp_lo}")
            check(f"Test {tn} HI={hi[0]:.3f}", ok_hi,
                  f"expected {exp_hi}")

    # ── Summary ──
    total = passed + failed
    print(f"\n{'=' * 40}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("All tests passed!")


if __name__ == "__main__":
    run_tests()
