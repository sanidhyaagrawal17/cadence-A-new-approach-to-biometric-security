import sys
from PyQt6.QtWidgets import QApplication
from frontend_ui.app_window import CadenceApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CadenceApp()
    window.show()
    sys.exit(app.exec())