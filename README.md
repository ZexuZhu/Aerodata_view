# Aerodata View — 气动数据可视化工具

基于 PyQt6 + matplotlib + pandas 构建的桌面应用，用于读取 Fluent CFD 气动数据 Excel，复现数据后处理流程，并提供交互式多曲线对比绘图与配平计算。

## 功能

### 数据处理
- 自动识别 Excel 中的 column 并区分 sheet 类型（部件/固定构型/舵面参数）
- 机体系 → 速度轴系力变换（Body → Wind frame）
- 无量纲化（CD, CL, CY, Cl, Cm, Cn）
- 重心平移修正（Cmnew, Cnnew，Xcg = -0.46）
- 百分比贡献（CD%, CL%）
- 派生变量：升阻比 E、续航因子 CL¹·⁵/CD、纵向静稳定度 dCm/dCL

### 可视化
- 左右分栏布局：左侧参数面板 + 右侧 4:3 绘图区
- 学术风格出图：Wong colorblind 色板、空心圆标记、minor ticks、去上/右 spine
- X/Y 轴变量自由选择（支持 19 个变量）
- 多 sheet × 多部件/构型 × 多 beta 同时对比
- 300ms 消抖自动重绘
- 交互式 zoom / pan / save（matplotlib toolbar）

### 配平计算
- 用户输入飞行速度、重量、参考舵偏角
- 自动计算配平舵偏 δe_trim、CL_trim、CD_trim、L/D_trim
- 输出升力损失%、阻力增加%、升阻比损失%

### 支持的 Sheet 类型

| 类型 | 特征 | 示例 |
|------|------|------|
| component | 原始力/力矩 + AB 列部件名 | 升降舵上偏10度部件数据 |
| precomputed | 无量纲系数，beta 伪部件 | 固定构型气动参数 |
| control_surface | 舵面六分量增量（dCD/dCL/…） | 舵面参数 |

## 安装

```bash
pip install -r requirements.txt
```

依赖：`pyqt6`, `pandas`, `openpyxl`, `matplotlib`, `numpy`

## 使用

```bash
python main.py
```

1. 点击「选择 Excel 文件」→ 程序自动读取全部 sheet
2. 勾选需要处理的 sheet → 点击「开始处理」
3. 左侧选择 X/Y 轴变量和部件/构型 → 右侧自动绘图
4. 可选：点击「验证计算」→ 随机 10 点对比 Python 与 Excel 结果
5. 可选：加载固定构型 + 舵面参数后，在底部「配平计算」输入 V/W/δref → 计算

## 绘图变量

| 变量 | 说明 | 可用范围 |
|------|------|----------|
| alpha | 攻角 (°) | 全部 |
| beta | 侧滑角 (°) | 全部 |
| CD, CL, CY | 阻力/升力/侧力系数 | 全部 |
| Cl, Cmnew, Cnnew | 滚转/俯仰/偏航力矩系数 (CG修正后) | 全部 |
| CD%, CL% | 占整机百分比 | 部件 sheet |
| E | 升阻比 CL/CD | 全部 |
| CL1.5/CD | 续航因子 | 全部 |
| dCm/dCL | 纵向静稳定度 | 固定构型 |
| dCD, dCL, dCY, dCl, dCm, dCn | 舵面六分量增量 | 舵面参数 |

## 项目结构

```
Aerodata_view/
├── main.py                    # 入口
├── requirements.txt
├── README.md
├── log.md                     # 开发日志
└── src/
    ├── data_loader.py         # Excel 读取 + sheet 类型识别
    ├── data_processor.py      # 气动计算管线
    ├── validator.py           # 验证（Python vs Excel）
    ├── plot_widget.py         # Matplotlib 画布
    ├── main_window.py         # UI 主窗口
    └── trim_calculator.py     # 配平计算
```

## 验证精度

随机抽样验证：Python 计算结果与 Excel 的差异在浮点精度极限（~3×10⁻¹⁶），可视为完全一致。
