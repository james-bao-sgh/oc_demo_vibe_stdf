"""
STDF data loading and caching module.
Parses STDF V4 files, extracts die/test data, caches as Parquet,
and registers with DuckDB for fast queries.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".stdf_cache")
CACHE_DIR.mkdir(exist_ok=True)

_duck_con: Optional[duckdb.DuckDBPyConnection] = None
_data_cache: Dict[str, Dict[str, Any]] = {}


def _get_cache_paths(filepath: str) -> Tuple[Path, Path, Path]:
    p = str(Path(filepath).absolute())
    h = hashlib.md5(p.encode()).hexdigest()
    return (
        CACHE_DIR / f"{h}_die.parquet",
        CACHE_DIR / f"{h}_test.parquet",
        CACHE_DIR / f"{h}_meta.json",
    )


def _get_duckdb() -> duckdb.DuckDBPyConnection:
    global _duck_con
    if _duck_con is None:
        _duck_con = duckdb.connect(":memory:")
    return _duck_con


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_stdf_raw(filepath: str):
    """Fast binary STDF parser — bypasses pystdf entirely.
    Only decodes the 5 record types we need (Wir/Pir/Prr/Ptr/Ftr).
    Falls back to pystdf on any error.
    """
    import bz2
    import struct
    from tqdm import tqdm

    path = Path(filepath)
    f = bz2.open(filepath, "rb") if filepath.endswith(".bz2") else open(filepath, "rb")
    data = memoryview(f.read())
    f.close()

    n = len(data)
    endian = '>'

    # Detect endian from FAR record (should always be first record)
    if n >= 9 and data[2] == 0 and data[3] == 10:
        cpu_type = data[4]
        if cpu_type == 2:
            endian = '<'

    # Columnar storage
    die_wafer_id: List[str] = []
    die_index: List[int] = []
    die_x: List[float] = []
    die_y: List[float] = []
    die_hard_bin: List[int] = []
    die_soft_bin: List[int] = []
    die_site: List[int] = []
    die_head: List[int] = []
    die_part_flg: List[int] = []

    test_wafer_id: List[str] = []
    test_die_index: List[int] = []
    test_name: List[str] = []
    test_num: List[int] = []
    test_result: List[float] = []
    test_lo_limit: List[Optional[float]] = []
    test_hi_limit: List[Optional[float]] = []
    test_units: List[str] = []
    test_site: List[int] = []
    test_head: List[int] = []

    wafer_id = "default_wafer"
    die_counter: Dict[int, int] = {}
    current_idx: Dict[int, int] = {}

    pos = 0
    pbar = tqdm(desc="Parsing", unit=" rec", mininterval=2, smoothing=0.1)
    ptr_count = 0

    while pos + 4 <= n:
        rec_len = struct.unpack_from(endian + 'H', data, pos)[0]
        rec_typ = data[pos + 2]
        rec_sub = data[pos + 3]
        body = pos + 4
        body_end = pos + 4 + rec_len

        if body_end > n:
            break

        # ── Ptr V4 (hot path, ~99% of records) ────────────────
        if rec_typ == 15 and rec_sub == 10:
            off = body
            if off + 12 > body_end:
                pos = body_end; continue

            tn = struct.unpack_from(endian + 'I', data, off)[0]
            hd = data[off + 4]
            st = data[off + 5]
            res = struct.unpack_from(endian + 'f', data, off + 8)[0]

            # Parse optional fields — any may be absent (pystdf fills with None)
            txt = ""
            lo: Optional[float] = None
            hi: Optional[float] = None
            units = ""
            off = body + 12

            # TEST_TXT (Cn)
            if off < body_end:
                slen = data[off]; off += 1
                if slen > 0 and off + slen <= body_end:
                    txt = data[off:off+slen].tobytes().decode('ascii', errors='replace')
                    off += slen

            # ALARM_ID (Cn) — skip
            if off < body_end:
                slen = data[off]; off += 1
                if slen > 0 and off + slen <= body_end:
                    off += slen

            # OPT_FLAG + scales
            if off + 4 <= body_end:
                off += 4  # OPT_FLAG(1) + RES_SCAL(1) + LLM_SCAL(1) + HLM_SCAL(1)
                # LO_LIMIT (R4) — read unconditionally (pystdf behavior, OPT_FLAG
                # may say absent but data is still present in the byte stream)
                if off + 4 <= body_end:
                    lo = struct.unpack_from(endian + 'f', data, off)[0]; off += 4
                    # HI_LIMIT (R4)
                    if off + 4 <= body_end:
                        hi = struct.unpack_from(endian + 'f', data, off)[0]; off += 4
                        # UNITS (Cn)
                        if off < body_end:
                            slen = data[off]; off += 1
                            if slen > 0 and off + slen <= body_end:
                                units = data[off:off+slen].tobytes().decode('ascii', errors='replace')
                                off += slen

            key = (hd << 16) | st
            di = current_idx.get(key)
            if di is not None:
                test_wafer_id.append(wafer_id)
                test_die_index.append(di)
                test_name.append((txt or f"Test_{tn}").strip())
                test_num.append(tn)
                test_result.append(res)
                test_lo_limit.append(lo)
                test_hi_limit.append(hi)
                test_units.append(units)
                test_site.append(st)
                test_head.append(hd)

            ptr_count += 1
            if ptr_count % 50000 == 0:
                pbar.update(50000)

        # ── Prr V4 ─────────────────────────────────────────────
        elif rec_typ == 5 and rec_sub == 20:
            off = body
            if off + 14 > body_end:
                pos = body_end; continue

            hd = data[off]; off += 1
            st = data[off]; off += 1
            pf = data[off]; off += 1
            off += 2  # NUM_TEST (U2)
            hb = struct.unpack_from(endian + 'H', data, off)[0]; off += 2
            sb = struct.unpack_from(endian + 'H', data, off)[0]; off += 2
            xc = struct.unpack_from(endian + 'h', data, off)[0]; off += 2
            yc = struct.unpack_from(endian + 'h', data, off)[0]; off += 2

            key = (hd << 16) | st
            di = current_idx.get(key)
            if di is not None:
                die_wafer_id.append(wafer_id)
                die_index.append(di)
                die_x.append(float(xc))
                die_y.append(float(yc))
                die_hard_bin.append(hb)
                die_soft_bin.append(sb)
                die_site.append(st)
                die_head.append(hd)
                die_part_flg.append(pf)

        # ── Pir ────────────────────────────────────────────────
        elif rec_typ == 5 and rec_sub == 10:
            hd = data[body]
            st = data[body + 1]
            key = (hd << 16) | st
            die_counter[key] = die_counter.get(key, 0) + 1
            current_idx[key] = die_counter[key]

        # ── Wir ────────────────────────────────────────────────
        elif rec_typ == 2 and rec_sub == 10:
            off = body + 6  # HEAD_NUM + SITE_GRP + START_T
            if off < body_end:
                slen = data[off]; off += 1
                if slen > 0 and off + slen <= body_end:
                    wafer_id = data[off:off+slen].tobytes().decode('ascii', errors='replace')
                    off += slen

        # ── Ftr V4 ─────────────────────────────────────────────
        elif rec_typ == 15 and rec_sub == 20:
            off = body
            if off + 24 > body_end:
                pos = body_end; continue

            tn = struct.unpack_from(endian + 'I', data, off)[0]
            hd = data[off + 4]
            st = data[off + 5]
            nf = struct.unpack_from(endian + 'I', data, off + 20)[0]

            key = (hd << 16) | st
            di = current_idx.get(key)
            if di is not None:
                test_wafer_id.append(wafer_id)
                test_die_index.append(di)
                test_name.append(f"FT_{tn}")
                test_num.append(tn)
                test_result.append(1.0 if nf == 0 else 0.0)
                test_lo_limit.append(None)
                test_hi_limit.append(None)
                test_units.append("")
                test_site.append(st)
                test_head.append(hd)

        pos = body_end

    pbar.close()

    if not die_index:
        raise ValueError("No die data found in STDF file")

    die_df = pd.DataFrame({
        "wafer_id": die_wafer_id,
        "die_index": die_index,
        "x_coord": die_x,
        "y_coord": die_y,
        "hard_bin": die_hard_bin,
        "soft_bin": die_soft_bin,
        "site": die_site,
        "head": die_head,
        "part_flg": die_part_flg,
    })

    if test_wafer_id:
        test_df = pd.DataFrame({
            "wafer_id": test_wafer_id,
            "die_index": test_die_index,
            "test_name": test_name,
            "test_num": test_num,
            "result": test_result,
            "low_limit": test_lo_limit,
            "high_limit": test_hi_limit,
            "units": test_units,
            "site": test_site,
            "head": test_head,
        })
    else:
        test_df = pd.DataFrame(columns=[
            "wafer_id", "die_index", "test_name", "test_num", "result",
            "low_limit", "high_limit", "units", "site", "head"
        ])

    return die_df, test_df, wafer_id


def parse_stdf(filepath: str) -> Dict[str, Any]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"STDF file not found: {filepath}")

    die_cache, test_cache, meta_cache = _get_cache_paths(filepath)

    if die_cache.exists() and test_cache.exists():
        logger.info(f"Loading cached Parquet for {filepath}")
        die_df = pd.read_parquet(die_cache)
        test_df = pd.read_parquet(test_cache)
        meta = {}
        if meta_cache.exists():
            import json
            with open(meta_cache) as f:
                meta = json.load(f)
        return _build_result(die_df, test_df, filepath, meta.get("wafer_id", "default_wafer"))

    # Fast path: custom binary parser (5-10x faster than pystdf)
    try:
        die_df, test_df, wafer_id = _parse_stdf_raw(filepath)
        die_df.to_parquet(die_cache)
        test_df.to_parquet(test_cache)
        import json
        with open(meta_cache, "w") as f:
            json.dump({"wafer_id": wafer_id}, f)
        return _build_result(die_df, test_df, filepath, wafer_id)
    except Exception as e:
        logger.warning(f"Fast parser failed ({e}), falling back to pystdf")

    # Fallback: pystdf-based parser
    logger.info("Falling back to pystdf parser")
    die_wafer_id: List[str] = []
    die_index: List[int] = []
    die_x: List[float] = []
    die_y: List[float] = []
    die_hard_bin: List[int] = []
    die_soft_bin: List[int] = []
    die_site: List[int] = []
    die_head: List[int] = []
    die_part_flg: List[int] = []

    test_wafer_id: List[str] = []
    test_die_index: List[int] = []
    test_name: List[str] = []
    test_num: List[int] = []
    test_result: List[float] = []
    test_lo_limit: List[Optional[float]] = []
    test_hi_limit: List[Optional[float]] = []
    test_units: List[str] = []
    test_site: List[int] = []
    test_head: List[int] = []

    wafer_id = "default_wafer"
    die_counter: Dict[int, int] = {}
    current_idx: Dict[int, int] = {}

    from pystdf.IO import Parser as StdfParser
    from pystdf import V4

    WIR_WAFER_ID = V4.Wir.WAFER_ID
    PIR_HEAD_NUM = V4.Pir.HEAD_NUM
    PIR_SITE_NUM = V4.Pir.SITE_NUM
    PRR_HEAD_NUM = V4.Prr.HEAD_NUM
    PRR_SITE_NUM = V4.Prr.SITE_NUM
    PRR_X_COORD = V4.Prr.X_COORD
    PRR_Y_COORD = V4.Prr.Y_COORD
    PRR_HARD_BIN = V4.Prr.HARD_BIN
    PRR_SOFT_BIN = V4.Prr.SOFT_BIN
    PRR_PART_FLG = V4.Prr.PART_FLG
    PTR_HEAD_NUM = V4.Ptr.HEAD_NUM
    PTR_SITE_NUM = V4.Ptr.SITE_NUM
    PTR_TEST_NUM = V4.Ptr.TEST_NUM
    PTR_TEST_TXT = V4.Ptr.TEST_TXT
    PTR_RESULT = V4.Ptr.RESULT
    PTR_LO_LIMIT = V4.Ptr.LO_LIMIT
    PTR_HI_LIMIT = V4.Ptr.HI_LIMIT
    PTR_UNITS = V4.Ptr.UNITS
    FTR_HEAD_NUM = V4.Ftr.HEAD_NUM
    FTR_SITE_NUM = V4.Ftr.SITE_NUM
    FTR_TEST_NUM = V4.Ftr.TEST_NUM
    _ftr_fail_idx: Optional[int] = None
    if hasattr(V4.Ftr, "fieldNames") and "FAIL_COUNT" in V4.Ftr.fieldNames:
        _ftr_fail_idx = V4.Ftr.fieldNames.index("FAIL_COUNT")

    import bz2
    f = bz2.open(filepath, "rb") if filepath.endswith(".bz2") else open(filepath, "rb")
    parser = StdfParser(V4.records, f)

    _pbar = None
    try:
        from tqdm import tqdm as _tqdm
        _pbar = _tqdm(desc="Parsing (pystdf)", unit=" rec", mininterval=2, smoothing=0.1)
    except ImportError:
        pass
    _ptr_count = 0

    class CollectSink:
        __slots__ = ()
        def before_send(self, source, data):
            nonlocal wafer_id, _ptr_count
            rec_type, fields = data

            if isinstance(rec_type, V4.Ptr):
                h = fields[PTR_HEAD_NUM]
                s = fields[PTR_SITE_NUM]
                key = h << 16 | s
                di = current_idx.get(key)
                if di is not None:
                    tn = fields[PTR_TEST_NUM]
                    txt = fields[PTR_TEST_TXT]
                    test_wafer_id.append(wafer_id)
                    test_die_index.append(di)
                    test_name.append((txt or f"Test_{tn}").strip())
                    test_num.append(tn)
                    test_result.append(float(fields[PTR_RESULT]))
                    test_lo_limit.append(_safe_float(fields[PTR_LO_LIMIT]))
                    test_hi_limit.append(_safe_float(fields[PTR_HI_LIMIT]))
                    test_units.append((fields[PTR_UNITS] or "").strip())
                    test_site.append(s)
                    test_head.append(h)
                _ptr_count += 1
                if _ptr_count % 50000 == 0:
                    if _pbar is not None:
                        _pbar.update(50000)
                    else:
                        logger.info(f"  ... parsed {_ptr_count} test results")

            elif isinstance(rec_type, V4.Prr):
                h = fields[PRR_HEAD_NUM]
                s = fields[PRR_SITE_NUM]
                key = h << 16 | s
                di = current_idx.get(key)
                if di is not None:
                    die_wafer_id.append(wafer_id)
                    die_index.append(di)
                    die_x.append(fields[PRR_X_COORD])
                    die_y.append(fields[PRR_Y_COORD])
                    die_hard_bin.append(fields[PRR_HARD_BIN])
                    die_soft_bin.append(fields[PRR_SOFT_BIN])
                    die_site.append(s)
                    die_head.append(h)
                    die_part_flg.append(fields[PRR_PART_FLG])

            elif isinstance(rec_type, V4.Ftr):
                h = fields[FTR_HEAD_NUM]
                s = fields[FTR_SITE_NUM]
                key = h << 16 | s
                di = current_idx.get(key)
                if di is not None:
                    tn = fields[FTR_TEST_NUM]
                    if _ftr_fail_idx is not None:
                        fail_cnt = fields[_ftr_fail_idx]
                    else:
                        fail_cnt = 0
                    test_wafer_id.append(wafer_id)
                    test_die_index.append(di)
                    test_name.append(f"FT_{tn}")
                    test_num.append(tn)
                    test_result.append(1.0 if fail_cnt == 0 else 0.0)
                    test_lo_limit.append(None)
                    test_hi_limit.append(None)
                    test_units.append("")
                    test_site.append(s)
                    test_head.append(h)

            elif isinstance(rec_type, V4.Wir):
                wid = fields[WIR_WAFER_ID]
                wafer_id = str(wid) if wid is not None else wafer_id

            elif isinstance(rec_type, V4.Pir):
                h = fields[PIR_HEAD_NUM]
                s = fields[PIR_SITE_NUM]
                key = h << 16 | s
                die_counter[key] = die_counter.get(key, 0) + 1
                current_idx[key] = die_counter[key]

        def after_send(self, source, data):
            pass

    sink = CollectSink()
    parser.addSink(sink)
    parser.parse()
    f.close()

    if _pbar is not None:
        _pbar.close()

    if not die_index:
        raise ValueError("No die data found in STDF file")

    die_df = pd.DataFrame({
        "wafer_id": die_wafer_id,
        "die_index": die_index,
        "x_coord": die_x,
        "y_coord": die_y,
        "hard_bin": die_hard_bin,
        "soft_bin": die_soft_bin,
        "site": die_site,
        "head": die_head,
        "part_flg": die_part_flg,
    })

    if test_wafer_id:
        test_df = pd.DataFrame({
            "wafer_id": test_wafer_id,
            "die_index": test_die_index,
            "test_name": test_name,
            "test_num": test_num,
            "result": test_result,
            "low_limit": test_lo_limit,
            "high_limit": test_hi_limit,
            "units": test_units,
            "site": test_site,
            "head": test_head,
        })
    else:
        test_df = pd.DataFrame(columns=[
            "wafer_id", "die_index", "test_name", "test_num", "result",
            "low_limit", "high_limit", "units", "site", "head"
        ])

    die_df.to_parquet(die_cache)
    test_df.to_parquet(test_cache)
    import json
    with open(meta_cache, "w") as f:
        json.dump({"wafer_id": wafer_id}, f)

    return _build_result(die_df, test_df, filepath, wafer_id)


def _build_result(
    die_df: pd.DataFrame,
    test_df: pd.DataFrame,
    filepath: str,
    wafer_id: str,
) -> Dict[str, Any]:
    wafers = die_df["wafer_id"].unique().tolist()
    test_items = sorted(test_df["test_name"].unique().tolist()) if not test_df.empty else []

    con = _get_duckdb()
    con.execute("DROP TABLE IF EXISTS die_info")
    con.execute("DROP TABLE IF EXISTS test_results")
    con.execute("CREATE TABLE die_info AS SELECT * FROM die_df")
    con.execute("CREATE TABLE test_results AS SELECT * FROM test_df")

    return {
        "filepath": filepath,
        "wafers": wafers,
        "current_wafer": wafer_id if wafer_id in wafers else (wafers[0] if wafers else None),
        "die_info": die_df,
        "test_results": test_df,
        "total_dies": len(die_df),
        "test_items": test_items,
    }


def get_wafer_data(data: Dict[str, Any], wafer_id: str) -> Dict[str, Any]:
    die_df = data["die_info"][data["die_info"]["wafer_id"] == wafer_id].copy()
    test_df = data["test_results"][data["test_results"]["wafer_id"] == wafer_id].copy()
    test_items = sorted(test_df["test_name"].unique().tolist()) if not test_df.empty else []

    return {
        "wafer_id": wafer_id,
        "die_info": die_df,
        "test_results": test_df,
        "test_items": test_items,
        "total_dies": len(die_df),
    }


def compute_cpk(test_df: pd.DataFrame, low_limit_col: str = "low_limit",
                high_limit_col: str = "high_limit") -> pd.DataFrame:
    if test_df.empty:
        return pd.DataFrame()

    con = _get_duckdb()
    con.execute("DROP TABLE IF EXISTS _cpk_input")
    con.execute("CREATE TABLE _cpk_input AS SELECT * FROM test_df")

    sql = f"""
    SELECT
        test_name,
        COUNT(*) AS n,
        AVG(result) AS mean,
        STDDEV_SAMP(result) AS sigma_samp,
        STDDEV_POP(result) AS sigma_pop,
        ANY_VALUE({low_limit_col}) AS lsl,
        ANY_VALUE({high_limit_col}) AS usl
    FROM _cpk_input
    WHERE result IS NOT NULL
      AND {low_limit_col} IS NOT NULL
      AND {high_limit_col} IS NOT NULL
      AND {low_limit_col} < {high_limit_col}
    GROUP BY test_name
    """
    try:
        stats = con.execute(sql).df()
    except Exception as e:
        logger.warning(f"Cpk computation failed: {e}")
        return pd.DataFrame()

    if stats.empty:
        return stats

    def _compute(row):
        usl = row["usl"]
        lsl = row["lsl"]
        mean = row["mean"]
        sig_s = row["sigma_samp"]
        sig_p = row["sigma_pop"]
        if sig_s is None or sig_s == 0:
            return row, float("inf"), float("inf")
        cpk_s = min((usl - mean), (mean - lsl)) / (3 * sig_s)
        cpk_p = min((usl - mean), (mean - lsl)) / (3 * sig_p) if sig_p and sig_p > 0 else float("inf")
        return row, cpk_s, cpk_p

    results = []
    for _, row in stats.iterrows():
        _, cpk, ppk = _compute(row)
        row["cpk"] = cpk
        row["ppk"] = ppk
        results.append(row)

    result_df = pd.DataFrame(results)
    return result_df.sort_values("cpk")


def generate_cgm_report() -> None:
    """Placeholder for CGM report generation."""
    pass


def clear_cache() -> None:
    _data_cache.clear()


def precache(filepath: str) -> Dict[str, Any]:
    """Parse and cache an STDF file, printing progress information."""
    import time
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return {}
    print(f"Pre-caching {filepath}...")
    t0 = time.time()
    result = parse_stdf(filepath)
    dt = time.time() - t0
    print(f"Done in {dt:.1f}s")
    print(f"  Wafers: {result['wafers']}")
    print(f"  Dies: {result['total_dies']}")
    print(f"  Test items: {len(result['test_items'])}")
    print(f"  Cache: {_get_cache_paths(filepath)[0].parent}")
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        precache(sys.argv[1])
    else:
        print("Usage: python data_loader.py <path_to.stdf>")
        print("       python data_loader.py <path_to.stdf.bz2>")
