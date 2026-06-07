"""绘图组件

将 matplotlib figure 嵌入 PyQt6，提供交互式气动数据曲线绘制。
学术风格：serif 字体、Wong colorblind 配色、空心圆标记、minor ticks、
去上/右 spine、frameless legend。
"""

import matplotlib
matplotlib.use("QtAgg")  # PyQt6 后端 — 必须在任何 pyplot import 之前

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator
from matplotlib import rcParams

# ================================================================
#  全局学术风格
# ================================================================

rcParams.update({
    # 字体：Microsoft YaHei（中文）+ DejaVu Sans（西文/数学）
    # sans-serif 回退链比 serif 更可靠地支持中文，避免 legend 方框
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans",
                        "Arial", "Helvetica"],
    "mathtext.fontset": "dejavusans",

    # 字体大小
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "legend.fontsize": 9,

    # 轴线
    "axes.linewidth": 1.2,
    "xtick.major.width": 1.0,
    "ytick.major.width": 1.0,
    "xtick.minor.width": 0.6,
    "ytick.minor.width": 0.6,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.major.size": 5,
    "ytick.major.size": 5,
    "xtick.minor.size": 2.5,
    "ytick.minor.size": 2.5,

    # 网格
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "grid.linewidth": 0.5,

    # 图例
    "legend.frameon": False,
})

# Wong (2011) colorblind-friendly 调色板 — Nature 系列常用
COLORS = [
    "#0072B2",  # 蓝
    "#E69F00",  # 橙
    "#009E73",  # 绿
    "#F0E442",  # 黄
    "#D55E00",  # 红棕
    "#CC79A7",  # 紫红
    "#56B4E9",  # 天蓝
    "#000000",  # 黑
]


class AeroCanvas(FigureCanvasQTAgg):
    """气动数据绘图画布，嵌入 PyQt6 界面。

    图面 4:3 比例 (8×6 inches @ 120 dpi)，学术风格。
    """

    def __init__(self, parent=None, width=8, height=6, dpi=120):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        # constrained_layout 自动防标签溢出，无需手动 subplots_adjust
        self.fig.set_constrained_layout(True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setMinimumSize(640, 480)

    def plot_curves(self, curves: dict, xlabel: str = "",
                    ylabel: str = "", title: str = "",
                    ylim: tuple | None = None):
        """绘制多条曲线。

        Args:
            curves: {legend_label: (x_array, y_array), ...}
            xlabel: X 轴标签
            ylabel: Y 轴标签
            title: 图表标题
        """
        self.ax.clear()

        if not curves:
            self.ax.text(0.5, 0.5, "请选择数据和变量",
                         ha="center", va="center",
                         transform=self.ax.transAxes, fontsize=14, color="gray")
            self.draw()
            return

        n_curves = len(curves)

        for i, (label, (x, y)) in enumerate(curves.items()):
            color = COLORS[i % len(COLORS)]
            self.ax.plot(
                x, y,
                marker="o",
                markersize=4,
                markerfacecolor="white",
                markeredgewidth=1.0,
                markeredgecolor=color,
                linewidth=1.5,
                label=label,
                color=color,
            )

        # --- 学术风格 ---
        # 去上/右 spine
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)

        # Minor ticks
        self.ax.xaxis.set_minor_locator(AutoMinorLocator(4))
        self.ax.yaxis.set_minor_locator(AutoMinorLocator(4))

        # 轴标签
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        if title:
            self.ax.set_title(title)

        # 网格
        self.ax.grid(True, which="major", alpha=0.25, linestyle="--", linewidth=0.5)
        self.ax.grid(True, which="minor", alpha=0.1, linestyle=":", linewidth=0.3)

        # Y 轴范围（手动指定时覆盖 auto）
        if ylim is not None:
            self.ax.set_ylim(ylim[0], ylim[1])

        # Legend
        if n_curves <= 6:
            self.ax.legend(loc="best")
        else:
            self.ax.legend(
                loc="upper left",
                bbox_to_anchor=(1.02, 1.0),
                fontsize=8,
            )

        self.draw()

    def clear_plot(self):
        """清空绘图区域。"""
        self.ax.clear()
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.text(0.5, 0.5, "请选择数据和变量",
                     ha="center", va="center",
                     transform=self.ax.transAxes, fontsize=14, color="gray")
        self.draw()
