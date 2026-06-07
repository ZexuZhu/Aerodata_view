"""验证器

随机选取数据点对比 Python 计算结果与 Excel 内置结果，
确保计算正确性。
"""

import random
import pandas as pd
import numpy as np

# 对比列映射：Python 计算列 → Excel 列
COMPARE_COLS = {
    "CD":    ("calc_CD",    "CD"),
    "CL":    ("calc_CL",    "CL"),
    "CY":    ("calc_CY",    "CY"),
    "Cl":    ("calc_Cl",    "Cl"),
    "Cm":    ("calc_Cm",    "Cm"),
    "Cn":    ("calc_Cn",    "Cn"),
    "Cmnew": ("calc_Cmnew", "Cmnew"),
    "Cnnew": ("calc_Cnnew", "Cnnew"),
    "CD%":   ("calc_CD%",   "CD%"),
    "CL%":   ("calc_CL%",   "CL%"),
}


def validate(processed_data: dict, excel_data: dict,
             n: int = 10, seed: int = 42) -> dict:
    """随机选取 n 个数据点进行验证。

    从所有已加载 sheet 的合并数据中随机选取行索引，
    对比 Python 计算结果与 Excel 结果。

    Args:
        processed_data: {sheet_name: DataFrame} Python 处理后的数据
        excel_data: {sheet_name: DataFrame} Excel 中的已处理数据
        n: 随机采样数量
        seed: 随机种子（保证可复现）

    Returns:
        dict: {
            "samples": [(sheet, row_idx, var, py_val, xl_val, abs_err, rel_err), ...],
            "all_pass": bool,
            "max_rel_error": float,
        }
    """
    random.seed(seed)
    np.random.seed(seed)

    # 收集所有可验证的 (sheet, row_index)
    candidates = []
    for sheet_name, proc_df in processed_data.items():
        if sheet_name not in excel_data:
            continue
        xls_df = excel_data[sheet_name]
        common_idx = proc_df.index.intersection(xls_df.index)
        for idx in common_idx:
            candidates.append((sheet_name, idx))

    if len(candidates) == 0:
        return {"samples": [], "all_pass": False,
                "max_rel_error": float("nan"),
                "error": "无可用数据（可能缺少 Excel 处理列）"}

    # 随机采样
    n_sample = min(n, len(candidates))
    chosen = random.sample(candidates, n_sample)

    samples = []
    max_rel_error = 0.0
    passed = 0
    total = 0

    for sheet_name, row_idx in chosen:
        proc_row = processed_data[sheet_name].loc[row_idx]
        xls_row = excel_data[sheet_name].loc[row_idx]

        for var_name, (calc_col, xls_col) in COMPARE_COLS.items():
            if calc_col not in proc_row or xls_col not in xls_row:
                continue
            py_val = proc_row[calc_col]
            xl_val = xls_row[xls_col]

            if pd.isna(py_val) or pd.isna(xl_val):
                continue

            abs_err = abs(py_val - xl_val)
            rel_err = abs_err / abs(xl_val) if abs(xl_val) > 1e-12 else abs_err

            samples.append({
                "sheet": sheet_name,
                "row": row_idx,
                "component": proc_row.get("__component__", "?"),
                "alpha": proc_row.get("alpha", "?"),
                "variable": var_name,
                "python_val": py_val,
                "excel_val": xl_val,
                "abs_error": abs_err,
                "rel_error": rel_err,
            })

            max_rel_error = max(max_rel_error, rel_err)
            total += 1
            if rel_err < 0.001:  # 0.1% tolerance
                passed += 1

    all_pass = (total > 0 and passed == total)

    return {
        "samples": samples,
        "all_pass": all_pass,
        "total_checks": total,
        "passed_checks": passed,
        "max_rel_error": max_rel_error,
    }
