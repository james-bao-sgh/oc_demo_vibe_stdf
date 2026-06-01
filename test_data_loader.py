"""
Standalone test for data_loader STDF parsing.

Clears cache, re-parses (timed), and verifies LSL/USL values
for known test items extracted by pystdf cross-check:
  - test 9207: LO=7.0, HI=7.65
  - test 9194: LO=3.85, HI=4.15
"""

import os
import sys
import time
from pathlib import Path

STDF_FILE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else r"C:\Users\aba1sgh\vibe_coding_demo\G2TVP150AC_8_5012114_09_5034758_MP3_TEMP_140_DEG_20250429_084931.std_20250616T195442000.bz2"
)


def test_parser(expected: dict = None):
    if expected is None:
        expected = {
            9207: (7.0, 7.65),
            9194: (3.85, 4.15),
        }

    # Import inside function so script can be run standalone
    sys.path.insert(0, str(Path(__file__).parent))
    import hashlib
    import pandas as pd
    from data_loader import _get_cache_paths, precache

    # ── 1. Clear cache ──
    die_cache, test_cache, meta_cache = _get_cache_paths(STDF_FILE)
    for p in [die_cache, test_cache, meta_cache]:
        if p.exists():
            p.unlink()
    print(f"Cache cleared for {STDF_FILE}")

    # ── 2. Parse (timed) ──
    t0 = time.time()
    result = precache(STDF_FILE)
    dt = time.time() - t0
    print(f"\nTotal parse time: {dt:.2f}s")
    print(f"  Dies: {result['total_dies']}")
    print(f"  Test items: {len(result['test_items'])}")

    # ── 3. Verify limits ──
    test_df = result["test_results"]
    errors = []

    for tn, (exp_lo, exp_hi) in expected.items():
        subset = test_df[test_df["test_num"] == tn]
        lo_vals = subset["low_limit"].dropna().unique()
        hi_vals = subset["high_limit"].dropna().unique()
        count = len(subset)

        print(f"\ntest_num={tn}: records={count}", end="")
        if len(lo_vals) == 0:
            print(", NO limits found")
            errors.append(f"{tn}: no limits in parsed data")
            continue

        got_lo = lo_vals[0]
        got_hi = hi_vals[0]
        ok_lo = abs(got_lo - exp_lo) < 0.001
        ok_hi = abs(got_hi - exp_hi) < 0.001

        lo_mark = "OK" if ok_lo else "FAIL"
        hi_mark = "OK" if ok_hi else "FAIL"
        print(f", LO={got_lo:.4f} (expected {exp_lo}) [{lo_mark}]"
              f", HI={got_hi:.4f} (expected {exp_hi}) [{hi_mark}]")

        if not ok_lo:
            errors.append(f"{tn} LO: got {got_lo}, expected {exp_lo}")
        if not ok_hi:
            errors.append(f"{tn} HI: got {got_hi}, expected {exp_hi}")

    # ── 4. Summary ──
    if errors:
        print(f"\nFAILED ({len(errors)} errors):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"\nALL {len(expected)} test items PASSED (parsed {result['total_dies']} dies in {dt:.1f}s)")
        sys.exit(0)


if __name__ == "__main__":
    test_parser()
