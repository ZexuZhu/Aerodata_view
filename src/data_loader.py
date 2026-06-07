"""Excel 数据加载器

读取 Fluent CFD 气动数据 Excel 文件，自动识别 sheet 类型：
- component: 有原始力/力矩 + 部件列 → 需体轴系变换处理
- precomputed: 直接有无量纲系数，无部件列 → 仅读取不处理
- skip: 结构不支持的 sheet → 跳过并警告
"""

import pandas as pd
import numpy as np

# 原始数据列（component sheet 必须存在）
REQUIRED_COLS = ["alpha", "beta", "vel", "Axis", "Normal", "Side",
                 "Roll", "Pitch", "Yaw"]

# Excel 已处理列（component sheet 验证用，可选）
EXCEL_PROCESSED_COLS = ["CD", "CL", "CY", "Cl", "Cm", "Cn",
                        "Cmnew", "Cnnew", "CD%", "CL%"]

# 参考参数列
REF_COLS = ["Sref", "Cref", "Bref"]

# 兜底参考参数
FALLBACK_REF = {"Sref": 0.27, "Cref": 0.105, "Bref": 2.55}


def get_sheet_names(file_path: str) -> list[str]:
    """读取 Excel 文件中所有 sheet 名称。"""
    xl = pd.ExcelFile(file_path)
    return xl.sheet_names


def load_excel(file_path: str, sheet_names: list[str]) -> dict:
    """加载指定 sheet 的数据，按类型分支处理。

    Returns:
        {
            "raw": {sheet_name: DataFrame},
            "excel": {sheet_name: DataFrame},
            "ref_params": {sheet_name: dict},
            "components": list[str],
            "sheet_types": {sheet_name: "component"|"precomputed"},
            "skipped": list[str],
        }
    """
    raw_data = {}
    excel_data = {}
    ref_params = {}
    sheet_types = {}
    skipped = []

    # 先尝试从"基本数据" sheet 读取参考参数
    global_ref = _read_basic_params(file_path)

    for name in sheet_names:
        try:
            df = pd.read_excel(file_path, sheet_name=name)
        except Exception as e:
            skipped.append(f"{name}（读取失败: {e}）")
            continue

        df.columns = [str(c).strip() if pd.notna(c) else "" for c in df.columns]

        s_type = _detect_sheet_type(df)

        if s_type == "component":
            _load_component_sheet(df, name, raw_data, excel_data, ref_params)
            sheet_types[name] = "component"

        elif s_type == "precomputed":
            _load_precomputed_sheet(df, name, raw_data, excel_data, ref_params, global_ref)
            sheet_types[name] = "precomputed"

        else:
            skipped.append(name)

    final_components = _merge_component_lists(raw_data)

    return {
        "raw": raw_data,
        "excel": excel_data,
        "ref_params": ref_params,
        "components": final_components,
        "sheet_types": sheet_types,
        "skipped": skipped,
    }


# ================================================================
#  分支处理
# ================================================================

def _load_component_sheet(df, name, raw_data, excel_data, ref_params):
    """加载部件 sheet：原始力 + AB 部件列 + 体轴系变换管线。"""
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Sheet '{name}' 缺少必要列: {missing}")

    # 参考参数
    ref = {}
    for col in REF_COLS:
        if col in df.columns:
            ref[col] = (df[col].iloc[0] if pd.notna(df[col].iloc[0])
                        else df[col].dropna().iloc[0])
    ref_params[name] = ref

    # 部件名列（AB）
    comp_idx = _find_component_column(df)
    if comp_idx is None:
        raise ValueError(f"Sheet '{name}' 中未找到部件名列")
    comp_series = df.iloc[:, comp_idx].copy()
    comp_series = comp_series.replace(r'^\s*$', np.nan, regex=True).ffill()
    df["__component__"] = comp_series

    # 原始数据
    raw_cols = REQUIRED_COLS + ["__component__"]
    raw_data[name] = df[raw_cols].copy()

    # Excel 验证列
    excel_cols = [c for c in EXCEL_PROCESSED_COLS if c in df.columns]
    if excel_cols:
        edf = df[excel_cols].copy()
        edf["__component__"] = df["__component__"]
        excel_data[name] = edf


def _load_precomputed_sheet(df, name, raw_data, excel_data, ref_params, global_ref):
    """加载固定构型 sheet：无量纲系数，无部件列，按 beta 分组。"""
    # 过滤无效行（alpha 和 beta 均为 NaN 的行 = 空行/trim 子块）
    df = df.dropna(subset=["alpha", "beta"], how="all").copy()

    # 参考参数
    ref = dict(global_ref)
    for col in REF_COLS:
        if col in df.columns:
            val = df[col].iloc[0] if pd.notna(df[col].iloc[0]) else df[col].dropna().iloc[0]
            ref[col] = val
    ref_params[name] = ref

    # beta 伪部件：β=0°, β=10° ...
    comp_labels = []
    for _, row in df.iterrows():
        b = row["beta"]
        if pd.notna(b):
            comp_labels.append(f"β={b:.0f}°")
        else:
            comp_labels.append("β=?")
    df["__component__"] = comp_labels

    # 原始数据列（精确匹配 + 模糊匹配含中文后缀的列）
    plot_cols = ["alpha", "beta", "vel", "CD", "CL", "CY", "Cl", "Cm", "Cn",
                 "Cmnew", "Cnnew", "E", "__component__"]
    # 模糊匹配特殊列名
    extra_patterns = {
        "Cl1.5/CD": ["Cl1.5/CD", "CL1.5/CD", "cl1.5/cd"],
        "dCm/dCL": ["dCm/dCL"],
    }
    for _, patterns in extra_patterns.items():
        for c in df.columns:
            cs = str(c).strip()
            if any(p in cs for p in patterns):
                if cs not in plot_cols:
                    plot_cols.append(cs)
                break
    available = [c for c in plot_cols if c in df.columns or c == "__component__"]
    raw_data[name] = df[available].copy()

    # Excel 验证列（存储所有数值列供参考，但不验证）
    excel_cols = [c for c in df.columns
                  if c not in REQUIRED_COLS and c != "__component__"
                  and pd.api.types.is_numeric_dtype(df[c])]
    if excel_cols:
        edf = df[excel_cols].copy()
        edf["__component__"] = df["__component__"]
        excel_data[name] = edf


# ================================================================
#  辅助函数
# ================================================================

def _detect_sheet_type(df: pd.DataFrame) -> str:
    """检测 sheet 类型。"""
    has_axis = "Axis" in df.columns
    has_cd = "CD" in df.columns
    has_component = _find_component_column(df) is not None

    if has_axis and has_component:
        return "component"
    elif has_cd and not has_axis:
        return "precomputed"
    else:
        return "skip"


def _read_basic_params(file_path: str) -> dict:
    """尝试从"基本数据" sheet 读取参考参数。"""
    try:
        df = pd.read_excel(file_path, sheet_name="基本数据")
    except (ValueError, Exception):
        return dict(FALLBACK_REF)

    # 基本数据 sheet 通常是 key-value 对（A 列参数名，B 列数值）
    if df.shape[1] < 2:
        return dict(FALLBACK_REF)

    params = dict(FALLBACK_REF)
    for _, row in df.iterrows():
        key = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        val = row.iloc[1] if pd.notna(row.iloc[1]) else None
        if val is None:
            continue
        if "Sref" in key or "参考面积" in key or "机翼面积" in key:
            params["Sref"] = float(val)
        elif "Cref" in key or "参考弦长" in key or "平均气动弦" in key:
            params["Cref"] = float(val)
        elif "Bref" in key or "参考展长" in key or "翼展" in key:
            params["Bref"] = float(val)
    return params


def _find_component_column(df: pd.DataFrame) -> int | None:
    """查找部件名列的列索引。"""
    for i, col in enumerate(df.columns):
        if col == "" or (isinstance(col, str) and col.startswith("Unnamed")):
            sample = df.iloc[:, i].dropna()
            if 0 < len(sample) < 50:
                return i
    for i, col in enumerate(df.columns):
        if isinstance(col, str) and ("部件" in col or "component" in col.lower()):
            return i
    if df.shape[1] >= 28:
        return 27
    return None


def _detect_components_from_series(comp_series: pd.Series) -> list[str]:
    """从部件列提取唯一部件名（按首次出现顺序）。"""
    valid = comp_series.dropna()
    unique = []
    seen = set()
    for name in valid:
        name = str(name).strip()
        if name and name not in seen:
            unique.append(name)
            seen.add(name)
    return unique


def _merge_component_lists(raw_data: dict) -> list[str]:
    """合并所有 sheet 的部件名。"""
    all_comps = []
    seen = set()
    for df in raw_data.values():
        if "__component__" in df.columns:
            for name in df["__component__"]:
                name = str(name).strip()
                if name and name not in seen:
                    all_comps.append(name)
                    seen.add(name)
    return all_comps
