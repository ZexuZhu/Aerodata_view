"""Aerodata View — 气动数据可视化工具

读取 Fluent CFD 气动数据 Excel，在 Python 中复现数据处理流程，
并提供交互式对比绘图功能。
"""

import sys
from PyQt6.QtWidgets import QApplication
from src.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Aerodata View")
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
