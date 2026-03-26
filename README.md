# CutPilot — AI 短视频智能剪辑工具

电商短视频 AI 副驾驶，从原始素材一键生成多版本带文案的短视频。

## 系统要求

- Python 3.13+
- Node.js 20+
- FFmpeg（已安装并在 PATH 中）
- FunASR（本地模型或 HTTP 服务）

## 快速开始

### 1. 安装 Python 依赖
```bash
cd ~/work/CutPilot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置
```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

### 3. 构建前端
```bash
cd webui
npm install
npm run build
cd ..
```

### 4. 运行
```bash
python main_webui.py
# 调试模式（显示开发者工具）:
python main_webui.py --debug
```

## 项目结构

```
CutPilot/
├── main_webui.py        # 应用入口 (pywebview)
├── core/                # Python 后端
│   ├── pipeline.py      # 处理流程编排
│   ├── asr.py           # 语音识别 (FunASR)
│   ├── director.py      # AI 脚本生成
│   ├── inspector.py     # AI 质量审核
│   ├── editor.py        # 视频剪辑 (MoviePy + FFmpeg)
│   ├── overlay.py       # Hook 文字叠加
│   ├── config.py        # 配置定义
│   ├── hwaccel.py       # 硬件加速检测
│   ├── history.py       # 处理历史
│   ├── license.py       # 授权管理
│   └── user_settings.py # 用户设置持久化
├── webui/               # Vue 3 前端
│   ├── src/
│   │   ├── views/       # 页面组件
│   │   ├── components/  # 共享组件
│   │   ├── stores/      # Pinia 状态管理
│   │   └── bridge.ts    # pywebview 桥接层
│   └── dist/            # 构建产物
├── config/
│   └── prompts/         # AI 提示词模板
└── CutPilot.spec        # PyInstaller 打包配置
```

## 打包

```bash
pyinstaller CutPilot.spec
# 产物在 dist/CutPilot.app (macOS) 或 dist/CutPilot/ (Windows)
```

## 技术栈

- **前端**: Vue 3 + Tailwind CSS + Material Symbols
- **桌面壳**: pywebview (Cocoa/WebKit)
- **AI**: OpenAI SDK → DeepSeek / 通义千问等
- **语音**: FunASR (SeACo-Paraformer + CAM++)
- **视频**: MoviePy + FFmpeg + 硬件加速
