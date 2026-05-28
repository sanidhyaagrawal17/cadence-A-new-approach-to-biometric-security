@echo off
cd /d "d:\cadence reboot v2"
"d:\cadence reboot v2\venv311\Scripts\python.exe" -c "import sys, os; sys.path.insert(0, os.getcwd()); from frontend_ui.views.face_setup import FaceSetupView; print('OK')"
