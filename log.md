# 开发日志

## 项目：Aerodata View — 气动数据可视化工具

### 2026-06-07 — 舵面参数 sheet 支持

**新增 control_surface 类型**
- 检测：有 dCD 且 dCL 列 → control_surface
- H-I 合并列提取构型名（ffill + strip）
- 过滤 Standard 块（仅保留 eleup10 / eledown10）
- Delta 列重命名：CY.1→dCY, Cl.1→dCl, Cm.1→dCm, Cn.1→dCn
- 新增绘图变量：dCD, dCL, dCY, dCl, dCm, dCn（19 变量总计）
- 模糊匹配仅限特殊变量，避免"CD"误匹配"dCD"

### 2026-06-07 — 扩充：固定构型气动参数 sheet

**data_loader 重构**
- `_detect_sheet_type()` — 自动识别 component/precomputed/skip
- precomputed 分支：beta 值作为伪部件（β=0°, β=10°），不验证
- skip 分支：无部件列且无特征列的 sheet 跳过并警告
- ref_params：优先从"基本数据" sheet 读取 → 兜底默认值

**data_processor 扩展**
- E (=CL/CD) 和 CL1.5/CD 始终可用
- dCm/dCL 仅 precomputed sheet 提供
- `resolve_column_name()` — 大小写不敏感 + 中文后缀模糊匹配
- precomputed sheet 不走处理管线，直接使用 Excel 列

**验证**
- 3 component sheets + 1 precomputed sheet 正确加载
- 11 分组（9 部件 + β=0° + β=10°）
- 90/90 验证通过，max rel error = 2.48e-16

### 2026-06-07 — UI 优化

**布局重构：上下 → 左右分栏**
- `QSplitter(Qt.Horizontal)` 替代根 QVBoxLayout
- 左侧：QScrollArea 参数面板（minWidth=280, maxWidth=400）
  - 部件复选框改为垂直排列
- 右侧：绘图区 AeroCanvas + toolbar
- Splitter: setCollapsible(0, False), stretchFactor 0/1
- 初始比例 320:960

**绘图学术风格化**
- 字体：Times New Roman + SimSun + STIX
- 配色：Wong (2011) colorblind 色板 (8色)
- 空心圆标记 (marker="o", mfc="white", mew=1.0)
- 去上/右 spine
- AutoMinorLocator(4) minor ticks
- Legend: ≤6条曲线内放 frameless，>6条外放
- Figure 8×6 inches @ 120 dpi (4:3)

### 2026-06-07 — 初始构建

#### 步骤 1：创建项目骨架
- 创建 `src/` 目录结构
- 编写 `requirements.txt`（pyqt6, pandas, openpyxl, matplotlib, numpy）
- 编写 `main.py` 入口

#### 步骤 2：实现 data_loader
- `get_sheet_names()` — 读取 Excel 全部 sheet 名称
- `load_excel()` — 按 sheet 加载原始数据
  - 列名标准化（去空格）
  - 必要列校验（alpha, beta, vel, Axis, Normal, Side, Roll, Pitch, Yaw）
  - 参考参数提取（Sref, Cref, Bref）
  - AB 列部件名自动识别（处理合并单元格：ffill + 空值过滤）
  - Excel 已处理列读取（用于验证）
- `_find_component_column()` — 智能定位部件名列（无header列 → 关键词 → 默认AB位置）

#### 步骤 3：实现 data_processor
- `process_sheet()` — 五步气动计算
  1. 速度轴系变换（Body → Wind）：Drag, Lift, Side_w
  2. 动压计算：Q = 0.5 × 1.225 × vel²
  3. 无量纲化：CD, CL, CY, Cl, Cm, Cn
  4. 重心修正：Cmnew = (Pitch + Normal×Xcg)/(Q·Sref·Cref), Cnnew = (Yaw - Side×Xcg)/(Q·Sref·Bref)
  5. 百分比贡献：CD% = CD_component / CD_整机 (同alpha)
- `PLOT_VARIABLES` — 可选绘图变量映射表
- 无"整机"时弹出警告并移除 CD%/CL%

#### 步骤 4：实现 validator
- 从所有 sheet 合并数据中随机抽取 10 行
- 对比 10 个变量（CD, CL, CY, Cl, Cm, Cn, Cmnew, Cnnew, CD%, CL%）
- 计算绝对误差和相对误差（容差 0.1%）
- 验证结果：**100/100 通过，最大相对误差 2.29e-16** ✅

#### 步骤 5：实现 plot_widget
- `AeroCanvas` — matplotlib FigureCanvasQTAgg 封装
- 中文支持（Microsoft YaHei, SimHei）
- 30 色配色循环（C0-C9 + tab10）
- Legend 放置在图外右侧
- 支持 NavigationToolbar2QT

#### 步骤 6：实现 main_window
- 文件选择 + sheet 复选框自动填充
- "开始处理" → 加载 + 计算 → 锁定 sheet → 显示部件复选框
- "重新读取" → 全部重置
- X/Y 轴下拉框（alpha, beta, CD, CL, CY, Cl, Cmnew, Cnnew, CD%, CL%）
- 部件复选框（全选/取消全选）
- 300ms 消抖自动重绘
- 验证结果 QDialog + QTableWidget

### 已知决议
- Xcg = -0.46 硬编码，不可更改
- 空气密度 ρ = 1.225 硬编码，不可更改
- 无"整机" → 警告并移除 CD%/CL%
- Sheet 选择：程序自动读取全部 sheet，用户复选框勾选
- 自动重绘：300ms 消抖
