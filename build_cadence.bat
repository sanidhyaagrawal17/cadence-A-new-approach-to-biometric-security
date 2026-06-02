@echo off
title Cadence Biometric Compiler & Packager
echo ==========================================
echo   CADENCE BIOMETRIC - MASTER BUILD SCRIPT
echo ==========================================
echo.

echo [1/4] Compiling CadenceCore via PyInstaller...
echo This will take a few minutes. Please wait...
pyinstaller --name "CadenceCore" --windowed --add-data "database;database" --add-data "core_ai;core_ai" --add-data "frontend_ui;frontend_ui" --collect-all tensorflow --collect-all cv2 main.py -y

echo.
echo [2/4] Injecting C++ Redistributable DLLs...
IF EXIST "dist\CadenceCore" (
    copy /Y "C:\Windows\System32\msvcp140.dll" "dist\CadenceCore\"
    copy /Y "C:\Windows\System32\vcruntime140.dll" "dist\CadenceCore\"
    copy /Y "C:\Windows\System32\vcruntime140_1.dll" "dist\CadenceCore\"
    echo [SUCCESS] Dependencies injected.
) ELSE (
    echo [ERROR] dist\CadenceCore folder not found! The PyInstaller build may have failed.
    pause
    exit /b
)

echo.
echo [3/4] Zipping the final folder for distribution...
echo Please wait, compressing gigabytes of AI models (this will take a few minutes)...
IF EXIST "CadenceCore_Portable.zip" del /F /Q "CadenceCore_Portable.zip"
powershell -command "Compress-Archive -Path 'dist\CadenceCore' -DestinationPath 'CadenceCore_Portable.zip' -Force"

echo.
echo [4/4] Build & Package Complete!
echo ==========================================
echo You will now see a file named "CadenceCore_Portable.zip" in your project folder.
echo Send THAT .zip file to your friend! They just need to extract it and double-click the .exe.
echo ==========================================
echo.
pause