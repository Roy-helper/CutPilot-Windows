@echo off
chcp 65001 >nul
title CutPilot 安装程序
cd /d "%~dp0"

echo.
echo  ===================================
echo    CutPilot AI 短视频剪辑工具
echo    安装中，请稍候...
echo  ===================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python
    echo 请先安装 Python 3.13+: https://www.python.org/downloads/
    echo 安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] Python 已安装

:: 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js
    echo 请先安装 Node.js 20+: https://nodejs.org/
    pause
    exit /b 1
)
echo [OK] Node.js 已安装

:: 检查 FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 FFmpeg
    echo 请安装 FFmpeg 并添加到 PATH
    echo 下载: https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)
echo [OK] FFmpeg 已安装

echo.
echo [1/3] 安装 Python 依赖...
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [错误] Python 依赖安装失败
    pause
    exit /b 1
)
echo [OK] Python 依赖安装完成

echo.
echo [2/3] 构建前端界面...
cd webui
call npm install --silent
call npm run build
cd ..
if errorlevel 1 (
    echo [错误] 前端构建失败
    pause
    exit /b 1
)
echo [OK] 前端构建完成

echo.
echo [3/3] 创建启动脚本...
if not exist .env (
    copy .env.example .env >nul
)

:: 创建启动脚本
(
echo @echo off
echo cd /d "%%~dp0"
echo call .venv\Scripts\activate.bat
echo python main_webui.py
) > start.bat

:: 创建桌面快捷方式
set "DESKTOP=%USERPROFILE%\Desktop"
(
echo @echo off
echo cd /d "%CD%"
echo call .venv\Scripts\activate.bat
echo start /b python main_webui.py
) > "%DESKTOP%\CutPilot.bat"

echo.
echo  ===================================
echo    安装完成！
echo  ===================================
echo.
echo  桌面已创建 CutPilot.bat，双击即可启动
echo.
echo  首次打开会显示激活界面：
echo  1. 复制你的机器码发给管理员
echo  2. 管理员会发回激活码
echo  3. 粘贴激活码点「激活」即可
echo.

set /p choice="是否现在启动？(Y/N) "
if /i "%choice%"=="Y" (
    call .venv\Scripts\activate.bat
    python main_webui.py
)

pause
