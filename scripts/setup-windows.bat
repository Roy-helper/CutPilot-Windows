@echo off
chcp 65001 >nul
title CutPilot 安装程序

echo.
echo  ===================================
echo    CutPilot AI 短视频剪辑工具
echo    一键安装脚本 (Windows)
echo  ===================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.13+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] Python 已安装

:: 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js 20+
    echo 下载地址: https://nodejs.org/
    pause
    exit /b 1
)
echo [OK] Node.js 已安装

:: 检查 FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 FFmpeg，请先安装
    echo 下载地址: https://www.gyan.dev/ffmpeg/builds/
    echo 下载后解压，将 bin 目录添加到系统 PATH
    pause
    exit /b 1
)
echo [OK] FFmpeg 已安装

:: 检查 Git
git --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Git，请先安装
    echo 下载地址: https://git-scm.com/download/win
    pause
    exit /b 1
)
echo [OK] Git 已安装

echo.
echo [1/4] 下载 CutPilot...
if exist "%USERPROFILE%\CutPilot" (
    echo 检测到已有安装，正在更新...
    cd /d "%USERPROFILE%\CutPilot"
    git pull origin master
) else (
    git clone https://github.com/Roy-helper/CutPilot.git "%USERPROFILE%\CutPilot"
    cd /d "%USERPROFILE%\CutPilot"
)

echo.
echo [2/4] 安装 Python 依赖（首次较慢）...
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q

echo.
echo [3/4] 构建前端界面...
cd webui
call npm install --silent
call npm run build
cd ..

echo.
echo [4/4] 配置文件...
if not exist .env (
    copy .env.example .env
    echo 已创建 .env 配置文件
    echo [重要] 请编辑 %USERPROFILE%\CutPilot\.env 填入你的 API Key
)

echo.
echo  ===================================
echo    安装完成！
echo  ===================================
echo.
echo  启动方式：双击 start.bat
echo  或运行：cd %USERPROFILE%\CutPilot ^&^& .venv\Scripts\activate ^&^& python main_webui.py
echo.

:: 创建启动脚本
(
echo @echo off
echo cd /d "%USERPROFILE%\CutPilot"
echo call .venv\Scripts\activate.bat
echo python main_webui.py
) > "%USERPROFILE%\CutPilot\start.bat"

:: 创建桌面快捷方式
(
echo @echo off
echo cd /d "%USERPROFILE%\CutPilot"
echo call .venv\Scripts\activate.bat
echo start /b python main_webui.py
) > "%USERPROFILE%\Desktop\CutPilot.bat"
echo 已在桌面创建 CutPilot.bat 快捷方式

echo.
echo 是否现在启动 CutPilot？(Y/N)
set /p choice=
if /i "%choice%"=="Y" (
    call .venv\Scripts\activate.bat
    python main_webui.py
)
