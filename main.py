import sys
import os
# Optional .env loader: use python-dotenv if installed to populate environment variables.
try:
    from dotenv import load_dotenv
    # Load .env from repository root if present
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)
except Exception:
    # If python-dotenv isn't available, continue without failing.
    pass

from PyQt6.QtWidgets import QApplication
from frontend_ui.app_window import CadenceApp

if __name__ == "__main__":
    # Developer override: disable liveness checks for now (temporary)
    import os
    os.environ.setdefault('DISABLE_LIVENESS', '1')
    app = QApplication(sys.argv)
    window = CadenceApp()
    window.show()
    sys.exit(app.exec())