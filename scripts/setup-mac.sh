#!/bin/bash
# CutPilot 一键安装脚本 (macOS)

set -e

echo ""
echo "  ==================================="
echo "    CutPilot AI 短视频剪辑工具"
echo "    一键安装脚本 (macOS)"
echo "  ==================================="
echo ""

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未检测到 Python3，请先安装:"
    echo "  brew install python@3.13"
    exit 1
fi
echo "[OK] Python3 已安装: $(python3 --version)"

# 检查 Node.js
if ! command -v node &>/dev/null; then
    echo "[错误] 未检测到 Node.js，请先安装:"
    echo "  brew install node"
    exit 1
fi
echo "[OK] Node.js 已安装: $(node --version)"

# 检查 FFmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "[错误] 未检测到 FFmpeg，请先安装:"
    echo "  brew install ffmpeg"
    exit 1
fi
echo "[OK] FFmpeg 已安装"

# 检查 Git
if ! command -v git &>/dev/null; then
    echo "[错误] 未检测到 Git，请先安装:"
    echo "  xcode-select --install"
    exit 1
fi
echo "[OK] Git 已安装"

INSTALL_DIR="$HOME/CutPilot"

echo ""
echo "[1/4] 下载 CutPilot..."
if [ -d "$INSTALL_DIR" ]; then
    echo "检测到已有安装，正在更新..."
    cd "$INSTALL_DIR"
    git pull origin master
else
    git clone https://github.com/Roy-helper/CutPilot.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo ""
echo "[2/4] 安装 Python 依赖（首次较慢）..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q

echo ""
echo "[3/4] 构建前端界面..."
cd webui
npm install --silent
npm run build
cd ..

echo ""
echo "[4/4] 配置文件..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "已创建 .env 配置文件"
    echo "[重要] 请编辑 $INSTALL_DIR/.env 填入你的 API Key"
fi

# 创建启动脚本
cat > "$INSTALL_DIR/start.sh" << 'LAUNCHER'
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python main_webui.py
LAUNCHER
chmod +x "$INSTALL_DIR/start.sh"

echo ""
echo "  ==================================="
echo "    安装完成！"
echo "  ==================================="
echo ""
echo "  启动方式: ~/CutPilot/start.sh"
echo ""

read -p "是否现在启动 CutPilot？(y/n) " choice
if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
    source .venv/bin/activate
    python main_webui.py
fi
