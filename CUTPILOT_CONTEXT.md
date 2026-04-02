# CutPilot-Windows Context

> 每次开启 CutPilot 开发会话时，先读这份文件恢复上下文。

## 项目概况

CutPilot 是一个 **Windows 桌面端短视频批量剪辑工具**，面向电商切片编辑师和 MCN 工作室。
核心流程：拖入长视频 → ASR 语音转文字 → AI 生成 3 版差异化脚本 → 质检去重 → FFmpeg 自动剪辑输出。

- **GitHub**: https://github.com/Roy-helper/CutPilot-Windows
- **GitHub 账号**: Roy-helper
- **本地仓库**: `C:\CutPilot-Windows`
- **Mac 原版** (不要动): `C:\CutPilot` / https://github.com/Roy-helper/CutPilot
- **用户数据目录**: `~/.cutpilot/` (settings.json, history.json, cache/)

## 技术栈

| 层 | 技术 | 版本要求 |
|----|------|----------|
| 桌面壳 | pywebview | >=5.0 |
| 前端 | Vue 3 + Pinia + Tailwind + TypeScript | Node >=20 |
| 构建 | Vite 7 | |
| 后端 | Python + Pydantic | >=3.10 (不用3.11+语法) |
| AI | OpenAI-compatible API (DeepSeek/Qwen/Kimi/MiniMax) | openai>=1.0 |
| ASR | faster-whisper (默认) / FunASR (可选) | |
| 视频 | MoviePy 2 + FFmpeg + 硬件加速 | |
| 打包 | PyInstaller --onedir | >=6.0 |

## 开发命令

```bash
cd C:/CutPilot-Windows

# Python 环境
.venv/Scripts/pip.exe install -r requirements.txt

# 前端构建（改了 webui/ 后必须跑）
cd webui && npm run build && cd ..

# 本地调试
.venv/Scripts/python.exe main_webui.py --debug

# 运行测试
.venv/Scripts/python.exe -m pytest tests/ -v

# 打包 EXE
.venv/Scripts/python.exe build.py
# 或直接用 spec:
.venv/Scripts/python.exe -m PyInstaller CutPilot.spec --noconfirm --clean

# 压缩分发
powershell -Command "Compress-Archive -Path 'C:\CutPilot-Windows\dist\CutPilot' -DestinationPath 'C:\Users\wzc66\Desktop\CutPilot-windows-x64.zip' -Force"
```

## 项目结构

```
C:\CutPilot-Windows/
├── main_webui.py              # 入口 (pywebview窗口 + PythonBridge API, 660行)
├── core/                      # Python 后端 (~6900行)
│   ├── pipeline.py            # 主流水线: ASR → Director → Inspector → Editor
│   ├── asr.py                 # 语音识别 (faster-whisper / FunASR)
│   ├── director.py            # AI 脚本生成 (DeepSeek API, JSON解析)
│   ├── inspector.py           # 质检 + 去重 + 敏感词过滤
│   ├── editor.py              # FFmpeg 剪辑 + 硬件加速编码
│   ├── ai_client.py           # OpenAI-compatible 客户端抽象
│   ├── config.py              # CutPilotConfig (pydantic-settings, CUTPILOT_前缀)
│   ├── models.py              # Sentence, ScriptVersion, ProcessResult, ExportOptions
│   ├── hwaccel.py             # GPU编码器检测 (NVENC > QSV > AMF > libx264)
│   ├── overlay.py             # 钩子文字叠加 (PIL + FFmpeg drawtext)
│   ├── cache_manager.py       # 按阶段缓存 (MD5 key)
│   ├── history.py             # 处理历史 (~/.cutpilot/history.json, 上限500)
│   ├── license.py             # HMAC 激活码验证 + 试用期
│   ├── category_detector.py   # 商品品类检测 (假发/美妆/护肤/服装)
│   ├── providers.py           # AI 供应商预设 (DeepSeek, Qwen, Kimi等)
│   ├── user_settings.py       # 用户偏好持久化
│   ├── paths.py               # 资源路径 (开发 vs PyInstaller)
│   ├── text_render.py         # PIL CJK文字卡片渲染
│   └── builtin_keys.py        # 内置API密钥 (.gitignore, 打包前手动创建)
│
├── webui/                     # Vue 3 前端 (~5000行)
│   └── src/
│       ├── App.vue            # 根布局 + 激活/设置状态机
│       ├── bridge.ts          # pywebview API 桥接 (含HTTP降级)
│       ├── views/
│       │   ├── ActivationView.vue   # 激活码输入
│       │   ├── SetupView.vue        # 首次设置 (选AI供应商+填Key)
│       │   ├── WorkspaceView.vue    # 主工作台 (拖入视频/处理/预览)
│       │   ├── HistoryView.vue      # 历史记录
│       │   └── SettingsView.vue     # 设置页 (ASR/编码器/画质)
│       ├── stores/
│       │   ├── workspace.ts         # 视频列表/版本/处理状态
│       │   └── notifications.ts     # Toast 通知
│       └── components/
│           ├── TopBar.vue           # 顶栏 + 授权徽章
│           └── SideNav.vue          # 左侧导航
│
├── config/
│   ├── prompts/
│   │   ├── sentence_selector.md     # Director 主提示词
│   │   ├── inspector.md             # 质检提示词
│   │   └── categories/              # 品类专属提示词 (wig/makeup/skincare/clothing)
│   └── sensitive_words.json         # 违禁词/敏感词/平台风险词
│
├── tests/                     # pytest 测试套件
│   ├── test_models.py         # 数据模型验证
│   ├── test_pipeline.py       # 全流程 + 缓存
│   ├── test_director.py       # AI JSON解析
│   ├── test_inspector.py      # 过滤/评分/去重
│   ├── test_editor.py         # 剪辑 + 编码
│   └── test_cache_manager.py  # 缓存序列化
│
├── docs/
│   ├── 2026-03-24-cutpilot-mvp-design.md   # MVP 产品设计文档
│   └── IMPLEMENTATION_PLAN.md               # 开发路线图
│
├── tools/generate_license.py  # 授权码生成
├── admin_tools.py             # 管理工具 (machine-id/gen/batch/activate)
├── build.py                   # PyInstaller 构建脚本
├── CutPilot.spec              # PyInstaller 配置
├── scripts/
│   ├── setup-windows.bat      # Windows 一键安装
│   └── setup-mac.sh           # macOS 一键安装
└── .env.example               # 环境变量模板
```

## 注意事项

1. **Python 3.10 兼容** — 不要用 `datetime.UTC`、`match/case` 等 3.11+ 语法
2. **core/builtin_keys.py** 在 .gitignore 里，不提交。打包前手动创建，含 DeepSeek/DashScope 密钥
3. **前端改完必须 `npm run build`** — pywebview 加载的是 `webui/dist/`
4. **git 配置** — user: Roy-helper / Roy-helper@users.noreply.github.com
5. **.NET 缺失时** — pywebview 自动降级为 Bottle HTTP + 系统浏览器模式
6. **默认画质 4K** — 用户可在设置页调整
7. **HuggingFace 被墙** — 模型下载走 hf-mirror.com

## 当前版本 v4.2.1 已完成功能

### 基础功能
- 视频缩略图预览 (ffmpeg 抓帧)
- ASR 引擎选择 (Faster Whisper / FunASR)
- 版本卡片完整展示 (封面标题 + 发布文案 + 标签)
- 批量复制全部文案
- 设置页离开未保存提醒
- GPU 并行数准确检测 (NVENC session limit)
- 每个视频输出到独立子文件夹
- .NET 缺失时自动降级浏览器模式
- 默认画质 4K

### 剪辑引擎升级 (MoviePy → 纯 FFmpeg)
- FFmpeg filter_complex 单 pass 剪辑 (trim→concat→speed)
- 零中间文件、零内存加载、流式处理
- 1.25x 加速版在同一 filter_complex 里一步完成，无二次编码画质损失
- Windows asyncio 隐患修复 (subprocess.run 替代 asyncio subprocess)

### 稳定性改造 (6项)
- GPU 诊断 + 编码器状态可见化 (diagnose_gpu API，前端绿/黄色点 + GPU型号)
- 中文路径全链路修复 (source + output 路径保护，overlay.py 迁移 subprocess.run)
- 批量处理异常隔离 + 汇总 (batch-summary 事件，per-video 错误展示)
- 取消处理完整清理 (Popen+轮询 cancel_event，terminate+kill，清理残留文件)
- ASR 模型下载体验 (进度条 + 10分钟超时 + 手动下载指引 + hf-mirror URL)
- VFR 视频兼容 (-fps_mode cfr + aresample=async=1 + VFR 检测 warning)

### UI 修复 (4项)
- 拖放功能接入 DOM (@dragover/@drop 事件 + 视觉反馈)
- 版本号统一为 v4.2
- 历史页空状态加"去工作台"跳转按钮
- 顶栏按钮精简 (清空/打开目录/复制文案收入"更多"下拉菜单)

### v4.2 新增功能 (10项)
- 无音频检测 — ASR 前 ffprobe 检测音频流，无音频立即报错
- AI 超时可配置 — config 加 ai_timeout=1800 (默认30分钟)，支持长视频
- 持久化日志 — rotating file handler 写 ~/.cutpilot/logs/，设置页"导出日志"按钮
- FFmpeg 缺失检测 — 启动时检测 PATH，缺失弹框提示下载链接
- AI JSON 重试 — Director JSON 解析失败最多重试 3 次，追加严格 JSON 提示
- SRT 字幕导出 — ASR 完成后自动在输出目录生成 .srt 文件
- 骨架屏 — 一键生成后立即显示 3 个 loading 骨架卡片
- 批量重试失败 — 失败视频卡片显示"重试"按钮，只重跑失败的
- 音频归一化 — FFmpeg loudnorm filter，统一 -14 LUFS (抖音标准)
- ASR 模型大小可选 — 设置页 tiny(快速)/small(默认)/medium(精准) 三档

### v4.2.1 体验打磨 (3项)
- API Key 连通性测试 — 测试连接显示延迟(ms)，错误分类(Key无效/超时/模型不存在)
- 错误信息友好化 — 6 类技术错误自动翻译为中文提示(文件不存在/编码器/内存/网络/API Key/无音频)
- 图标 tooltip — 所有 icon-only 按钮加 title 悬停提示(通知/账户/预览/复制/选中等)

## 测试覆盖

- **198 个测试**，全部通过
- **覆盖率 63%** (core/ 模块)
- 100% 覆盖: models, config, cache_manager, history, category_detector, providers
- 90%+ 覆盖: pipeline (96%), ai_client (95%), user_settings (92%), paths (91%)
- 手动测试清单: `docs/manual_test_checklist.md`

## 代码规模

- 后端 (core/): ~3,900 行 Python
- 前端 (webui/src/): ~2,800 行 TypeScript/Vue
- 入口 (main_webui.py): ~720 行
- 测试 (tests/): ~2,400 行
- **总计: ~9,800 行** (不含测试约 7,400 行)

## 目标用户

做切片的电商视频编辑师，核心需求是"快、批量、不出错"。产品不要做重。
