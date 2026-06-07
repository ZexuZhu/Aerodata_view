"""主窗口

气动数据可视化工具的主界面。
左右分栏布局：左侧参数面板，右侧 4:3 绘图区。
"""

import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QCheckBox, QLabel,
    QFileDialog, QGroupBox, QMessageBox, QDialog,
    QTableWidget, QTableWidgetItem, QDialogButtonBox, QDoubleSpinBox,
    QScrollArea, QFrame, QSplitter, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from src.data_loader import get_sheet_names, load_excel
from src.data_processor import (process_all, PLOT_VARIABLES,
                                get_plot_variables, resolve_column_name)
from src.validator import validate
from src.plot_widget import AeroCanvas
from src.trim_calculator import calculate_trim, RHO

DEBOUNCE_MS = 300


class MainWindow(QMainWindow):
    """主窗口 — 左右分栏布局"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aerodata View — 气动数据可视化")

        # --- 内部状态 ---
        self._file_path: str = ""
        self._all_sheet_names: list[str] = []
        self._raw_data: dict = {}
        self._processed_data: dict = {}
        self._excel_data: dict = {}
        self._ref_params: dict = {}
        self._components: list[str] = []
        self._has_whole_aircraft: bool = False
        self._processing_done: bool = False
        self._sheet_types: dict = {}
        self._has_precomputed: bool = False
        self._has_control_surface: bool = False
        self._standard_baseline: dict = {}
        self._trim_available: bool = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_plot)

        self._sheet_checkboxes: dict[str, QCheckBox] = {}
        self._component_checkboxes: dict[str, QCheckBox] = {}

        self._build_ui()

    # ================================================================
    #  UI 构建
    # ================================================================

    def _build_ui(self):
        # ---- 根 Splitter（水平分栏） ----
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self._splitter)

        # 左侧：参数面板
        left = self._build_left_panel()
        self._splitter.addWidget(left)

        # 右侧：绘图区
        right = self._build_right_panel()
        self._splitter.addWidget(right)

        # Splitter 比例：左侧固定，右侧拉伸
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([320, 960])

    def _build_left_panel(self) -> QScrollArea:
        """构建左侧参数面板（可滚动）。"""
        scroll = QScrollArea()
        scroll.setMinimumWidth(280)
        scroll.setMaximumWidth(400)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # ---- 文件选择 ----
        file_group = QGroupBox("文件")
        file_layout = QVBoxLayout(file_group)
        self._btn_file = QPushButton("选择 Excel 文件")
        self._btn_file.clicked.connect(self._on_select_file)
        self._label_file = QLabel("未选择")
        self._label_file.setStyleSheet("color: gray; font-size: 11px;")
        self._label_file.setWordWrap(True)
        file_layout.addWidget(self._btn_file)
        file_layout.addWidget(self._label_file)
        layout.addWidget(file_group)

        # ---- Sheet 选择 ----
        sheet_group = QGroupBox("Sheet 选择")
        sheet_layout = QVBoxLayout(sheet_group)

        sheet_btn_row = QHBoxLayout()
        btn_all_s = QPushButton("全选")
        btn_all_s.clicked.connect(lambda: self._toggle_all_sheets(True))
        btn_none_s = QPushButton("取消")
        btn_none_s.clicked.connect(lambda: self._toggle_all_sheets(False))
        btn_all_s.setFixedWidth(50)
        btn_none_s.setFixedWidth(50)
        sheet_btn_row.addWidget(btn_all_s)
        sheet_btn_row.addWidget(btn_none_s)
        sheet_btn_row.addStretch()
        sheet_layout.addLayout(sheet_btn_row)

        self._sheet_list = QWidget()
        self._sheet_list_layout = QVBoxLayout(self._sheet_list)
        self._sheet_list_layout.setSpacing(2)
        self._sheet_list_layout.setContentsMargins(0, 0, 0, 0)
        sheet_layout.addWidget(self._sheet_list)

        self._label_sheet_hint = QLabel("（选择文件后显示 sheet 列表）")
        self._label_sheet_hint.setStyleSheet("color: gray; font-size: 11px;")
        sheet_layout.addWidget(self._label_sheet_hint)

        layout.addWidget(sheet_group)

        # ---- 处理按钮 ----
        proc_row = QHBoxLayout()
        self._btn_process = QPushButton("开始处理")
        self._btn_process.clicked.connect(self._on_process)
        self._btn_process.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 5px 16px; }")
        self._btn_process.setEnabled(False)
        self._btn_reload = QPushButton("重新读取")
        self._btn_reload.clicked.connect(self._on_reload)
        self._btn_reload.setEnabled(False)
        proc_row.addWidget(self._btn_process)
        proc_row.addWidget(self._btn_reload)
        layout.addLayout(proc_row)

        # ---- 绘图设置 ----
        axis_group = QGroupBox("绘图变量")
        axis_layout = QGridLayout(axis_group)
        axis_layout.addWidget(QLabel("X 轴:"), 0, 0)
        self._combo_x = QComboBox()
        self._combo_x.addItems(list(PLOT_VARIABLES.keys()))
        self._combo_x.setCurrentText("alpha")
        self._combo_x.currentTextChanged.connect(self._schedule_replot)
        axis_layout.addWidget(self._combo_x, 0, 1)
        axis_layout.addWidget(QLabel("Y 轴:"), 1, 0)
        self._combo_y = QComboBox()
        self._combo_y.addItems(list(PLOT_VARIABLES.keys()))
        self._combo_y.setCurrentText("CD")
        self._combo_y.currentTextChanged.connect(self._schedule_replot)
        axis_layout.addWidget(self._combo_y, 1, 1)
        layout.addWidget(axis_group)

        # ---- 部件选择 ----
        comp_group = QGroupBox("部件选择")
        comp_layout = QVBoxLayout(comp_group)

        comp_btn_row = QHBoxLayout()
        self._btn_comp_all = QPushButton("全选")
        self._btn_comp_all.clicked.connect(lambda: self._toggle_all_comps(True))
        self._btn_comp_none = QPushButton("取消")
        self._btn_comp_none.clicked.connect(lambda: self._toggle_all_comps(False))
        self._btn_comp_all.setFixedWidth(50)
        self._btn_comp_none.setFixedWidth(50)
        self._btn_comp_all.setEnabled(False)
        self._btn_comp_none.setEnabled(False)
        comp_btn_row.addWidget(self._btn_comp_all)
        comp_btn_row.addWidget(self._btn_comp_none)
        comp_btn_row.addStretch()
        comp_layout.addLayout(comp_btn_row)

        self._comp_list = QWidget()
        self._comp_layout = QVBoxLayout(self._comp_list)
        self._comp_layout.setSpacing(2)
        self._comp_layout.setContentsMargins(0, 0, 0, 0)
        comp_layout.addWidget(self._comp_list)

        self._label_comp_hint = QLabel("（处理后显示部件列表）")
        self._label_comp_hint.setStyleSheet("color: gray; font-size: 11px;")
        comp_layout.addWidget(self._label_comp_hint)

        layout.addWidget(comp_group)

        # ---- 验证按钮 ----
        self._btn_validate = QPushButton("验证计算")
        self._btn_validate.clicked.connect(self._on_validate)
        self._btn_validate.setEnabled(False)
        layout.addWidget(self._btn_validate)

        # ---- 配平计算 ----
        trim_group = QGroupBox("配平计算")
        trim_layout = QVBoxLayout(trim_group)

        # 输入行
        trim_input = QGridLayout()
        trim_input.addWidget(QLabel("V (m/s):"), 0, 0)
        self._trim_V = self._make_spin(30, 1, 200, 1, "m/s")
        trim_input.addWidget(self._trim_V, 0, 1)
        trim_input.addWidget(QLabel("W (N):"), 1, 0)
        self._trim_W = self._make_spin(10, 0.1, 10000, 1, "N")
        trim_input.addWidget(self._trim_W, 1, 1)
        trim_input.addWidget(QLabel("δref (°):"), 2, 0)
        self._trim_dref = self._make_spin(10, 1, 90, 1, "°")
        trim_input.addWidget(self._trim_dref, 2, 1)
        trim_layout.addLayout(trim_input)

        self._btn_trim = QPushButton("计算配平")
        self._btn_trim.clicked.connect(self._on_trim_calc)
        self._btn_trim.setEnabled(False)
        trim_layout.addWidget(self._btn_trim)

        # 结果
        self._label_trim_result = QLabel("")
        self._label_trim_result.setStyleSheet("font-size: 11px; line-height: 1.5;")
        self._label_trim_result.setWordWrap(True)
        trim_layout.addWidget(self._label_trim_result)
        self._label_trim_hint = QLabel("（需加载固定构型 + 舵面参数）")
        self._label_trim_hint.setStyleSheet("color: gray; font-size: 10px;")
        trim_layout.addWidget(self._label_trim_hint)

        layout.addWidget(trim_group)

        # ---- 状态 ----
        self._label_status = QLabel("")
        self._label_status.setStyleSheet("color: gray; font-size: 11px;")
        self._label_status.setWordWrap(True)
        layout.addWidget(self._label_status)

        layout.addStretch()
        scroll.setWidget(panel)
        return scroll

    def _build_right_panel(self) -> QWidget:
        """构建右侧绘图区。"""
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._canvas = AeroCanvas(self, width=8, height=6, dpi=120)
        layout.addWidget(self._canvas, 1)
        return right

    # ================================================================
    #  事件处理
    # ================================================================

    def _on_select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择气动数据 Excel 文件", "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*)")
        if not path:
            return

        self._file_path = path
        self._label_file.setText(os.path.basename(path))
        self._label_file.setStyleSheet("font-size: 11px;")

        try:
            self._all_sheet_names = get_sheet_names(path)
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"无法读取 Excel 文件：\n{e}")
            return

        # 填充 sheet 复选框（垂直排列）
        self._clear_sheet_checkboxes()
        self._label_sheet_hint.setVisible(False)
        for name in self._all_sheet_names:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_sheet_check_changed)
            self._sheet_checkboxes[name] = cb
            self._sheet_list_layout.addWidget(cb)

        self._btn_process.setEnabled(True)
        self._btn_reload.setEnabled(False)
        self._label_status.setText(
            f"已加载 {len(self._all_sheet_names)} 个 sheet，勾选后点击「开始处理」")
        self._label_status.setStyleSheet("color: #2196F3; font-size: 11px;")

    def _on_sheet_check_changed(self):
        if self._processing_done:
            self._schedule_replot()

    def _on_process(self):
        selected = self._get_selected_sheets()
        if not selected:
            QMessageBox.warning(self, "未选择", "请至少勾选一个 sheet。")
            return

        self._btn_process.setEnabled(False)
        self._label_status.setText("正在读取和处理数据...")
        self._label_status.setStyleSheet("color: #FF9800; font-size: 11px;")
        self.repaint()

        try:
            result = load_excel(self._file_path, selected)
        except Exception as e:
            QMessageBox.critical(self, "处理失败", f"读取数据时出错：\n{e}")
            self._btn_process.setEnabled(True)
            self._label_status.setText("处理失败，请重试")
            self._label_status.setStyleSheet("color: red; font-size: 11px;")
            return

        self._raw_data = result["raw"]
        self._excel_data = result["excel"]
        self._ref_params = result["ref_params"]
        self._components = result["components"]
        self._sheet_types = result.get("sheet_types", {})
        self._has_precomputed = "precomputed" in self._sheet_types.values()
        self._has_control_surface = "control_surface" in self._sheet_types.values()
        self._standard_baseline = result.get("standard_baseline", {})
        self._trim_available = (self._has_precomputed and self._has_control_surface)
        self._btn_trim.setEnabled(self._trim_available)
        if not self._trim_available:
            self._label_trim_hint.setText("（需加载固定构型 + 舵面参数）")
        else:
            self._label_trim_hint.setText("")

        try:
            self._processed_data = process_all(
                self._raw_data, self._ref_params, self._sheet_types)
        except Exception as e:
            QMessageBox.critical(self, "计算失败", f"气动计算时出错：\n{e}")
            self._btn_process.setEnabled(True)
            self._label_status.setText("计算失败，请重试")
            self._label_status.setStyleSheet("color: red; font-size: 11px;")
            return

        # 仅 component sheet 需要"整机"检测
        has_component_sheets = "component" in self._sheet_types.values()
        if has_component_sheets:
            self._has_whole_aircraft = "整机" in self._components
            if not self._has_whole_aircraft:
                QMessageBox.warning(
                    self, "缺少整机数据",
                    "未找到「整机」部件，CD% 和 CL% 将不可用。\n"
                    "下拉菜单中的 CD%/CL% 选项将被移除。")
                self._remove_percentage_vars()

        # 动态追加 precomputed 专属变量
        self._update_plot_variables()

        # 锁定 sheet 复选框
        for cb in self._sheet_checkboxes.values():
            cb.setEnabled(False)

        self._populate_component_checkboxes()

        self._processing_done = True
        self._btn_reload.setEnabled(True)
        self._btn_validate.setEnabled(True)

        skipped = result.get("skipped", [])
        skip_msg = ""
        if skipped:
            skip_msg = f"  ⚠ 跳过: {', '.join(skipped)}"
        self._label_status.setText(
            f"完成：{len(self._raw_data)} sheet, {len(self._components)} 分组, "
            f"{sum(len(df) for df in self._processed_data.values())} 行{skip_msg}")
        self._label_status.setStyleSheet("color: #4CAF50; font-size: 11px;")

        self._splitter.setSizes([320, 960])
        self._do_plot()

    def _on_reload(self):
        self._raw_data = {}
        self._processed_data = {}
        self._excel_data = {}
        self._ref_params = {}
        self._components = []
        self._has_whole_aircraft = False
        self._processing_done = False
        self._sheet_types = {}
        self._has_precomputed = False
        self._has_control_surface = False
        self._standard_baseline = {}
        self._trim_available = False
        self._btn_trim.setEnabled(False)
        self._label_trim_result.setText("")
        self._label_trim_hint.setText("（需加载固定构型 + 舵面参数）")

        for cb in self._sheet_checkboxes.values():
            cb.setEnabled(True)

        self._clear_component_checkboxes()
        self._label_comp_hint.setVisible(True)

        self._combo_x.clear()
        self._combo_y.clear()
        base_vars = list(PLOT_VARIABLES.keys())
        self._combo_x.addItems(base_vars)
        self._combo_y.addItems(base_vars)
        self._combo_x.setCurrentText("alpha")
        self._combo_y.setCurrentText("CD")

        self._btn_process.setEnabled(True)
        self._btn_reload.setEnabled(False)
        self._btn_validate.setEnabled(False)
        self._btn_comp_all.setEnabled(False)
        self._btn_comp_none.setEnabled(False)
        self._label_status.setText("已重置")
        self._label_status.setStyleSheet("color: gray; font-size: 11px;")

        self._canvas.clear_plot()

    def _on_validate(self):
        if not self._processed_data:
            QMessageBox.warning(self, "无数据", "请先处理数据。")
            return

        result = validate(self._processed_data, self._excel_data, n=10)

        if "error" in result:
            QMessageBox.warning(self, "验证失败", result["error"])
            return

        dlg = ValidationDialog(result, self)
        dlg.exec()

    # ================================================================
    #  绘图调度
    # ================================================================

    def _schedule_replot(self):
        self._debounce_timer.start(DEBOUNCE_MS)

    def _do_plot(self):
        if not self._processing_done or not self._processed_data:
            return

        x_var = self._combo_x.currentText()
        y_var = self._combo_y.currentText()

        if not x_var or not y_var:
            return

        selected_sheets = self._get_selected_sheets()
        selected_comps = self._get_selected_components()

        curves = {}
        for sheet in selected_sheets:
            if sheet not in self._processed_data:
                continue
            df = self._processed_data[sheet]

            # 根据实际列名解析（precomputed sheet 无 calc_ 前缀）
            df_cols = df.columns.tolist()
            x_col = resolve_column_name(x_var, df_cols)
            y_col = resolve_column_name(y_var, df_cols)

            for comp in selected_comps:
                comp_df = df[df["__component__"] == comp]
                if len(comp_df) == 0:
                    continue
                comp_df = comp_df.sort_values("alpha")
                x_data = (comp_df[x_col].values if x_col in comp_df.columns
                          else comp_df["alpha"].values)
                y_data = (comp_df[y_col].values if y_col in comp_df.columns
                          else [])
                if len(y_data) == 0:
                    continue
                label = f"{sheet}_{comp}"
                curves[label] = (x_data, y_data)

        # dCm/dCL 特殊 Y 轴范围
        ylim = (-30, 0) if y_var == "dCm/dCL" else None

        self._canvas.plot_curves(curves, xlabel=x_var, ylabel=y_var,
                                 title=f"{y_var} vs {x_var}", ylim=ylim)

    # ================================================================
    #  辅助方法
    # ================================================================

    def _get_selected_sheets(self) -> list[str]:
        return [n for n, cb in self._sheet_checkboxes.items() if cb.isChecked()]

    def _get_selected_components(self) -> list[str]:
        return [n for n, cb in self._component_checkboxes.items() if cb.isChecked()]

    def _toggle_all_sheets(self, checked: bool):
        for cb in self._sheet_checkboxes.values():
            if cb.isEnabled():
                cb.setChecked(checked)

    def _toggle_all_comps(self, checked: bool):
        for cb in self._component_checkboxes.values():
            cb.setChecked(checked)
        self._schedule_replot()

    def _clear_sheet_checkboxes(self):
        for cb in self._sheet_checkboxes.values():
            self._sheet_list_layout.removeWidget(cb)
            cb.deleteLater()
        self._sheet_checkboxes.clear()

    def _clear_component_checkboxes(self):
        for cb in self._component_checkboxes.values():
            self._comp_layout.removeWidget(cb)
            cb.deleteLater()
        self._component_checkboxes.clear()

    def _populate_component_checkboxes(self):
        self._clear_component_checkboxes()
        self._label_comp_hint.setVisible(False)
        for comp in self._components:
            cb = QCheckBox(comp)
            cb.setChecked(True)
            cb.stateChanged.connect(self._schedule_replot)
            self._component_checkboxes[comp] = cb
            self._comp_layout.addWidget(cb)

        self._btn_comp_all.setEnabled(True)
        self._btn_comp_none.setEnabled(True)

    @staticmethod
    def _make_spin(default, minv, maxv, step, suffix):
        """快速创建 QDoubleSpinBox。"""
        sp = QDoubleSpinBox()
        sp.setRange(minv, maxv)
        sp.setValue(default)
        sp.setSingleStep(step)
        sp.setSuffix(f" {suffix}")
        sp.setDecimals(1)
        return sp

    def _on_trim_calc(self):
        """执行配平计算。"""
        if not self._trim_available:
            return

        V = self._trim_V.value()
        W = self._trim_W.value()
        dref = self._trim_dref.value()

        # 获取固定构型 β=0° 数据
        baseline = None
        for name, df in self._processed_data.items():
            if self._sheet_types.get(name) == "precomputed":
                # 取 β=0° 子集
                comps = df["__component__"].unique()
                beta0_comp = [c for c in comps if "β=0" in str(c)]
                if beta0_comp:
                    bdf = df[df["__component__"] == beta0_comp[0]].sort_values("alpha")
                else:
                    bdf = df.sort_values("alpha")
                # 需要 CL/CD/Cmnew — precomputed sheet 有这些列
                # 使用 resolve_column_name 查找
                cl_col = resolve_column_name("CL", bdf.columns.tolist())
                cd_col = resolve_column_name("CD", bdf.columns.tolist())
                cm_col = resolve_column_name("Cmnew", bdf.columns.tolist())
                if cl_col in bdf.columns and cd_col in bdf.columns and cm_col in bdf.columns:
                    baseline = {
                        "alpha": bdf["alpha"].values,
                        "CL": bdf[cl_col].values,
                        "CD": bdf[cd_col].values,
                        "Cmnew": bdf[cm_col].values,
                    }
                break

        if baseline is None:
            QMessageBox.warning(self, "无基准数据", "未找到固定构型气动参数数据。")
            return

        # 获取舵面参数
        cs = None
        for name, df in self._processed_data.items():
            if self._sheet_types.get(name) == "control_surface":
                # 根据 Cm 符号选方向
                cs_alpha = df["alpha"].values
                cs_comps = df["__component__"].unique()
                # 在 range 中取 Cm 符号
                cl_arr = baseline["CL"]
                mid_idx = len(cl_arr) // 2
                cm_mid = baseline["Cmnew"][mid_idx]

                if cm_mid > 0:
                    target = [c for c in cs_comps if "eleup" in str(c).lower()]
                else:
                    target = [c for c in cs_comps if "eledown" in str(c).lower()]
                if not target:
                    QMessageBox.warning(self, "舵面数据", "未找到匹配的舵面构型。")
                    return

                cs_df = df[df["__component__"] == target[0]].sort_values("alpha")
                dcd_col = resolve_column_name("dCD", cs_df.columns.tolist())
                dcl_col = resolve_column_name("dCL", cs_df.columns.tolist())
                dcm_col = resolve_column_name("dCm", cs_df.columns.tolist())
                cs = {
                    "alpha": cs_df["alpha"].values,
                    "dCD": cs_df[dcd_col].values,
                    "dCL": cs_df[dcl_col].values,
                    "dCm": cs_df[dcm_col].values,
                }
                break

        if cs is None:
            QMessageBox.warning(self, "无舵面数据", "未找到舵面参数数据。")
            return

        # 计算
        try:
            r = calculate_trim(V, W, dref, baseline, cs)
        except ValueError as e:
            QMessageBox.warning(self, "配平失败", str(e))
            return

        if r is None:
            QMessageBox.warning(self, "配平失败", "计算未收敛，请检查输入参数。")
            return

        self._label_trim_result.setText(
            f"α_req = {r['alpha_req']:.2f}°  |  "
            f"δe_trim = {r['delta_trim']:+.2f}°  |  "
            f"CL_req = {r['CL_req']:.4f}\n"
            f"CL_trim = {r['CL_trim']:.4f}  |  "
            f"CD_trim = {r['CD_trim']:.4f}  |  "
            f"L/D_trim = {r['LD_trim']:.2f}\n"
            f"L/D_base = {r['LD_base']:.2f}  |  "
            f"CL损失 = {r['CL_loss_pct']:.1f}%  |  "
            f"CD增加 = {r['CD_inc_pct']:.1f}%  |  "
            f"L/D损失 = {r['LD_loss_pct']:.1f}%"
        )

    def _remove_percentage_vars(self):
        for combo in [self._combo_x, self._combo_y]:
            for var in ["CD%", "CL%"]:
                idx = combo.findText(var)
                if idx >= 0:
                    combo.removeItem(idx)

    def _update_plot_variables(self):
        """根据已加载 sheet 类型动态更新变量下拉列表。"""
        vars_dict = get_plot_variables(self._has_precomputed,
                                        self._has_control_surface)
        current_x = self._combo_x.currentText()
        current_y = self._combo_y.currentText()

        self._combo_x.clear()
        self._combo_y.clear()
        self._combo_x.addItems(list(vars_dict.keys()))
        self._combo_y.addItems(list(vars_dict.keys()))

        if current_x in vars_dict:
            self._combo_x.setCurrentText(current_x)
        else:
            self._combo_x.setCurrentText("alpha")
        if current_y in vars_dict:
            self._combo_y.setCurrentText(current_y)
        else:
            self._combo_y.setCurrentText("CD")


class ValidationDialog(QDialog):
    """验证结果弹窗"""

    def __init__(self, result: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("验证结果")
        self.resize(900, 450)

        layout = QVBoxLayout(self)

        samples = result.get("samples", [])
        total = result.get("total_checks", 0)
        passed = result.get("passed_checks", 0)
        max_err = result.get("max_rel_error", 0)

        status_text = (
            f"随机选取 {len(set(s['row'] for s in samples))} 个数据点，"
            f"共 {total} 项对比  |  "
            f"通过: {passed}/{total}  |  "
            f"最大相对误差: {max_err:.6f}"
        )
        if result.get("all_pass", False):
            status_text += "  ✅ 验证通过"
        else:
            status_text += "  ❌ 存在超出容差的项"

        label = QLabel(status_text)
        font = QFont()
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)

        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels(
            ["Sheet", "行号", "部件", "alpha", "变量",
             "Python 值", "Excel 值", "相对误差"])
        table.setRowCount(len(samples))

        for i, s in enumerate(samples):
            table.setItem(i, 0, QTableWidgetItem(str(s["sheet"])))
            table.setItem(i, 1, QTableWidgetItem(str(s["row"] + 1)))
            table.setItem(i, 2, QTableWidgetItem(str(s["component"])))
            table.setItem(i, 3, QTableWidgetItem(str(s["alpha"])))
            table.setItem(i, 4, QTableWidgetItem(s["variable"]))
            table.setItem(i, 5, QTableWidgetItem(f"{s['python_val']:.8f}"))
            table.setItem(i, 6, QTableWidgetItem(f"{s['excel_val']:.8f}"))
            rel_item = QTableWidgetItem(f"{s['rel_error']:.6e}")
            if s["rel_error"] >= 0.001:
                rel_item.setForeground(Qt.GlobalColor.red)
            else:
                rel_item.setForeground(Qt.GlobalColor.darkGreen)
            table.setItem(i, 7, rel_item)

        table.resizeColumnsToContents()
        layout.addWidget(table)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.close)
        layout.addWidget(btn_box)
