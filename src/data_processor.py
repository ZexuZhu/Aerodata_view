"""气动数据处理器

在 Python 中复现 Excel 的数据处理流程：
1. 机体系 → 速度轴系力变换
2. 动压计算
3. 无量纲化（气动系数）
4. 重心平移修正（Cmnew, Cnnew）
5. 百分比贡献（CD%, CL%）
"""

import numpy as np
import pandas as pd

# 物理常数（不可更改）
RHO = 1.225        # 空气密度 kg/m³
XCG_REF = -0.46    # 参考重心位置 m


def process_sheet(raw_df: pd.DataFrame, ref_params: dict) -> pd.DataFrame:
    """对单个 sheet 的原始数据执行全部气动计算。

    Args:
        raw_df: 含原始列 (alpha, beta, vel, Axis, Normal, Side,
                Roll, Pitch, Yaw, __component__) 的 DataFrame
        ref_params: {"Sref": float, "Cref": float, "Bref": float}

    Returns:
        含所有计算结果的 DataFrame，计算列以 calc_ 为前缀
    """
    df = raw_df.copy()

    Sref = ref_params["Sref"]
    Cref = ref_params["Cref"]
    Bref = ref_params["Bref"]

    # 单位转换：alpha, beta 从度转弧度
    alpha_rad = np.radians(df["alpha"].values)
    beta_rad = np.radians(df["beta"].values)

    cos_a = np.cos(alpha_rad)
    sin_a = np.sin(alpha_rad)
    cos_b = np.cos(beta_rad)
    sin_b = np.sin(beta_rad)

    Axis = df["Axis"].values
    Normal = df["Normal"].values
    Side = df["Side"].values
    Roll = df["Roll"].values
    Pitch = df["Pitch"].values
    Yaw = df["Yaw"].values
    vel = df["vel"].values

    # --- Step 1: 速度轴系变换 (Body → Wind frame) ---
    drag = (Axis * cos_a * cos_b
            + Normal * sin_a * cos_b
            + Side * sin_b)
    lift = -Axis * sin_a + Normal * cos_a
    side_w = (-Axis * cos_a * sin_b
              + Side * cos_b
              - Normal * sin_a * sin_b)

    # --- Step 2: 动压 ---
    q = 0.5 * RHO * vel ** 2

    # --- Step 3: 无量纲化 ---
    df["calc_Drag"] = drag
    df["calc_Lift"] = lift
    df["calc_Side_w"] = side_w
    df["calc_Q"] = q
    df["calc_CD"] = -drag / (q * Sref)
    df["calc_CL"] = -lift / (q * Sref)
    df["calc_CY"] = side_w / (q * Sref)
    df["calc_Cl"] = Roll / (q * Sref * Bref)
    df["calc_Cm"] = Pitch / (q * Sref * Cref)
    df["calc_Cn"] = Yaw / (q * Sref * Bref)

    # --- Step 4: 重心平移修正 ---
    df["calc_Cmnew"] = (Pitch + Normal * XCG_REF) / (q * Sref * Cref)
    df["calc_Cnnew"] = (Yaw - Side * XCG_REF) / (q * Sref * Bref)

    # --- Step 5: 派生变量 ---
    # 升阻比 E = CL / CD
    df["calc_E"] = np.where(df["calc_CD"].values != 0,
                            df["calc_CL"].values / df["calc_CD"].values,
                            np.nan)
    # 续航因子 CL^1.5 / CD
    df["calc_CL15_CD"] = np.where(df["calc_CD"].values != 0,
                                  np.abs(df["calc_CL"].values) ** 1.5
                                  * np.sign(df["calc_CL"].values)
                                  / df["calc_CD"].values,
                                  np.nan)

    return df


def compute_percentages(processed_data: dict) -> dict:
    """计算 CD% 和 CL%（相对于整机的百分比贡献）。

    对每个 sheet 内的每个 alpha，用该 alpha 下"整机"的 CD/CL 作为参考。

    Args:
        processed_data: {sheet_name: DataFrame} 经过 process_sheet 的数据

    Returns:
        {sheet_name: DataFrame} 含 calc_CD% 和 calc_CL% 列的数据
    """
    for sheet_name, df in processed_data.items():
        # 查找"整机"部件的数据
        whole = df[df["__component__"] == "整机"]
        if len(whole) == 0:
            continue

        # 构建 alpha → 整机 CD/CL 映射
        whole_cd = dict(zip(whole["alpha"], whole["calc_CD"]))
        whole_cl = dict(zip(whole["alpha"], whole["calc_CL"]))

        cd_pct = []
        cl_pct = []
        for _, row in df.iterrows():
            alpha = row["alpha"]
            comp = row["__component__"]
            if comp == "整机":
                cd_pct.append(1.0)
                cl_pct.append(1.0)
            elif alpha in whole_cd and whole_cd[alpha] != 0:
                cd_pct.append(row["calc_CD"] / whole_cd[alpha])
                cl_pct.append(row["calc_CL"] / whole_cl[alpha])
            else:
                cd_pct.append(np.nan)
                cl_pct.append(np.nan)

        df["calc_CD%"] = cd_pct
        df["calc_CL%"] = cl_pct

    return processed_data


def process_all(raw_data: dict, ref_params: dict,
                sheet_types: dict | None = None) -> dict:
    """处理数据：component sheet 走管线，precomputed 直接使用。

    Args:
        raw_data: {sheet_name: DataFrame}
        ref_params: {sheet_name: {Sref, Cref, Bref}}
        sheet_types: {sheet_name: "component"|"precomputed"}

    Returns:
        {sheet_name: DataFrame}
    """
    processed = {}
    for sheet_name, df in raw_data.items():
        s_type = sheet_types.get(sheet_name, "component") if sheet_types else "component"
        if s_type == "precomputed":
            # precomputed sheet 不处理，直接使用 Excel 列
            processed[sheet_name] = df.copy()
        else:
            processed[sheet_name] = process_sheet(df, ref_params[sheet_name])
    processed = compute_percentages(processed)
    return processed


# 可供用户选择绘图的变量列表（展示名 → 列名）
# calc_* 前缀 = Python 计算；无前缀 = 直接读 Excel（precomputed sheet）
PLOT_VARIABLES = {
    "alpha":    "alpha",
    "beta":     "beta",
    "CD":       "calc_CD",
    "CL":       "calc_CL",
    "CY":       "calc_CY",
    "Cl":       "calc_Cl",
    "Cmnew":    "calc_Cmnew",
    "Cnnew":    "calc_Cnnew",
    "CD%":      "calc_CD%",
    "CL%":      "calc_CL%",
    "E":        "calc_E",
    "CL1.5/CD": "calc_CL15_CD",
}

# precomputed sheet 专属变量（映射到 Excel 原始列名）
PRECOMPUTED_VARS = {
    "dCm/dCL": "dCm/dCL",
}

def get_plot_variables(has_precomputed: bool = False) -> dict:
    """返回当前可用的绘图变量。

    Args:
        has_precomputed: 是否加载了 precomputed 类型 sheet

    Returns:
        {显示名: 列名}
    """
    vars_dict = dict(PLOT_VARIABLES)
    if has_precomputed:
        vars_dict.update(PRECOMPUTED_VARS)
    return vars_dict

def resolve_column_name(var_name: str, df_columns: list) -> str:
    """根据变量名和 DataFrame 实际列，解析正确的列名。

    precomputed sheet 的列名可能含中文后缀（如 "dCm/dCL稳定性"），
    需要模糊匹配。
    """
    # 精确匹配
    if var_name in PRECOMPUTED_VARS:
        target = PRECOMPUTED_VARS[var_name]
        if target in df_columns:
            return target
    if var_name in PLOT_VARIABLES:
        col = PLOT_VARIABLES[var_name]
        if col in df_columns:
            return col
        # precomputed 回退：去 calc_ 前缀
        if col.startswith("calc_") and col[5:] in df_columns:
            return col[5:]

    # 模糊匹配（大小写不敏感，处理中文后缀如 "dCm/dCL稳定性"）
    vn_lower = var_name.lower()
    for c in df_columns:
        cs = str(c).lower()
        if vn_lower in cs or cs.startswith(vn_lower):
            return c

    return var_name
