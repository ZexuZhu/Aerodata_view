"""交互式配平计算

利用固定构型基准数据 + 舵面增量数据，
计算给定飞行条件下的配平舵偏角及气动性能变化。
"""

import numpy as np

RHO = 1.225  # kg/m³


def calculate_trim(V: float, W: float, delta_ref: float,
                   baseline: dict, control_surface: dict,
                   sref: float = 0.27) -> dict | None:
    """计算配平状态。

    Args:
        V: 飞行速度 m/s
        W: 起飞重量 N
        delta_ref: 舵面参考偏角 °（用于缩放 dCm/dCL/dCD 到 per-degree）
        baseline: {
            "alpha": array,
            "CL": array,
            "CD": array,
            "Cmnew": array,   # CG 修正后的俯仰力矩系数
        }
        control_surface: {
            "alpha": array,
            "dCL": array,     # @ delta_ref 度的升力增量
            "dCD": array,     # @ delta_ref 度的阻力增量
            "dCm": array,     # @ delta_ref 度的俯仰力矩增量
        }
        sref: 参考面积 m²

    Returns:
        dict 配平结果, 或 None（输入无效）
    """
    if delta_ref == 0:
        return None

    # --- 1. 动压 & 需求 CL ---
    q = 0.5 * RHO * V ** 2
    if q <= 0:
        return None
    CL_req = W / (q * sref)

    # --- 2. 检查 CL 范围 ---
    cl_min, cl_max = baseline["CL"].min(), baseline["CL"].max()
    if CL_req < cl_min or CL_req > cl_max:
        raise ValueError(
            f"所需 CL={CL_req:.4f} 超出可用范围 [{cl_min:.4f}, {cl_max:.4f}]。\n"
            f"请调整飞行速度或重量。")

    # --- 3. 从 CL(α) 反查 α_req ---
    alpha_arr = np.asarray(baseline["alpha"], dtype=float)
    CL_arr = np.asarray(baseline["CL"], dtype=float)
    CD_arr = np.asarray(baseline["CD"], dtype=float)
    Cm_arr = np.asarray(baseline["Cmnew"], dtype=float)

    alpha_req = float(np.interp(CL_req, CL_arr, alpha_arr))

    # --- 4. 插值基准值 ---
    CD_base = float(np.interp(alpha_req, alpha_arr, CD_arr))
    Cm_base = float(np.interp(alpha_req, alpha_arr, Cm_arr))

    # --- 5. 插值舵面增量 ---
    cs_alpha = np.asarray(control_surface["alpha"], dtype=float)
    dCL_arr = np.asarray(control_surface["dCL"], dtype=float)
    dCD_arr = np.asarray(control_surface["dCD"], dtype=float)
    dCm_arr = np.asarray(control_surface["dCm"], dtype=float)

    dCL_raw = float(np.interp(alpha_req, cs_alpha, dCL_arr))
    dCD_raw = float(np.interp(alpha_req, cs_alpha, dCD_arr))
    dCm_raw = float(np.interp(alpha_req, cs_alpha, dCm_arr))

    # --- 6. 缩放为 per-degree ---
    dCL_ddeg = dCL_raw / delta_ref
    dCD_ddeg = dCD_raw / delta_ref
    dCm_ddeg = dCm_raw / delta_ref

    # --- 7. 配平舵偏 ---
    if abs(dCm_ddeg) < 1e-12:
        return None  # 舵面无操纵效能
    delta_trim = -Cm_base / dCm_ddeg

    # --- 8~9. 配平 CL, CD ---
    CL_trim = CL_req + dCL_ddeg * delta_trim
    CD_trim = CD_base + dCD_ddeg * delta_trim

    # --- 10~11. 升阻比 ---
    LD_trim = CL_trim / CD_trim if CD_trim != 0 else float("inf")
    LD_base = CL_req / CD_base if CD_base != 0 else float("inf")

    # --- 12~14. 损失百分比 ---
    dCL_from_elevator = abs(dCL_ddeg * delta_trim)
    CL_loss_pct = dCL_from_elevator / CL_req * 100 if CL_req != 0 else 0
    CD_inc_pct = (CD_trim - CD_base) / CD_base * 100 if CD_base != 0 else 0
    LD_loss_pct = (LD_base - LD_trim) / LD_base * 100 if LD_base != 0 else 0

    return {
        "V": V,
        "W": W,
        "delta_ref": delta_ref,
        "q": q,
        "CL_req": CL_req,
        "alpha_req": alpha_req,
        "delta_trim": delta_trim,
        "CL_trim": CL_trim,
        "CD_trim": CD_trim,
        "CD_base": CD_base,
        "Cm_base": Cm_base,
        "LD_trim": LD_trim,
        "LD_base": LD_base,
        "CL_loss_pct": CL_loss_pct,
        "CD_inc_pct": CD_inc_pct,
        "LD_loss_pct": LD_loss_pct,
    }
