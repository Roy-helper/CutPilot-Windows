#!/bin/bash
# CutPilot 安装脚本 (macOS)
# 解压 zip 后在 CutPilot 目录里运行: bash install.sh

set -e
cd "$(dirname "$0")"

echo ""
echo "  ==================================="
echo "    CutPilot AI 短视频剪辑工具"
echo "    安装中，请稍候..."
echo "  ==================================="
echo ""

# 检查依赖
for cmd in python3 node ffmpeg; do
    if ! command -v $cmd &>/dev/null; then
        echo "[错误] 未检测到 $cmd"
        echo "请运行: brew install python@3.13 node ffmpeg"
        exit 1
    fi
done
echo "[OK] 依赖检查通过"

echo ""
echo "[1/3] 安装 Python 依赖..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q
echo "[OK] Python 依赖安装完成"

echo ""
echo "[2/3] 构建前端界面..."
cd webui
npm install --silent
npm run build
cd ..
echo "[OK] 前端构建完成"

echo ""
echo "[3/3] 创建配置..."
[ ! -f .env ] && cp .env.example .env

# 创建启动脚本
cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python main_webui.py
EOF
chmod +x start.sh

echo ""
echo "  ==================================="
echo "    安装完成！"
echo "  ==================================="
echo ""
echo "  启动: ./start.sh"
echo ""
echo "  首次打开会显示激活界面："
echo "  1. 复制你的机器码发给管理员"
echo "  2. 管理员会发回激活码"
echo "  3. 粘贴激活码点「激活」即可"
echo ""

read -p "是否现在启动？(y/n) " choice
[ "$choice" = "y" ] || [ "$choice" = "Y" ] && ./start.sh
