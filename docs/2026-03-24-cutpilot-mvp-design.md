# CutPilot — AI 副驾驶 MVP 设计文档

**Date**: 2026-03-24
**Status**: Approved
**Product**: CutPilot — AI 副驾驶（电商短视频智能剪辑工具）

## 一、产品概述

### 定位
面向抖音/快手电商卖家和切片达人的本地桌面软件。用户拖入直播/产品素材视频，AI 自动生成 3 个不同角度的成品短视频，每个版本附带发布文案、封面标题、标签，直接复制到平台发布。

### 核心价值
- 一个素材 → 3 个差异化版本（防同质化限流）
- 自动生成文案/标题/标签（不用想词）
- 本地处理（隐私安全，不上传视频）
- 普通电脑即可运行（无需 GPU）

### 目标用户
- 抖音小商家（日发 5-20 条视频）
- 无货源带货达人
- MCN 机构矩阵运营

### 商业模式（MVP 阶段）
- 月订阅制，API Key 硬编码在客户端（后续迁移到云端授权）
- MVP 阶段手动发放激活码

## 二、技术架构

### 架构图

```
┌─ CutPilot 桌面应用 (PySide6) ────────────────────┐
│                                                    │
│  UI 层 (ui/)                                       │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ 拖拽导入  │ │  进度展示     │ │ 成品预览+导出 │   │
│  └────┬─────┘ └──────┬───────┘ └──────┬───────┘   │
│       │              │                │            │
│  核心层 (core/)      │                │            │
│  ┌──────────┐ ┌──────┴───────┐ ┌──────┴───────┐   │
│  │ ASR 识别  │ │ AI 编导+质检  │ │ FFmpeg 剪辑   │   │
│  │ (本地)    │ │ (API 调用)   │ │ (本地)        │   │
│  └──────────┘ └──────────────┘ └──────────────┘   │
│                      │                             │
└──────────────────────┼─────────────────────────────┘
                       │ HTTPS
                       ↓
               DeepSeek API (deepseek-v3)
```

### 数据流

```
用户拖入视频.mp4
  → ASR 识别（本地 FunASR，CPU 模式 ~90 秒/3 分钟视频）
  → 生成编号字幕列表（Sentence 对象）
  → AI 编导（DeepSeek API，~15 秒）
     - 输出 3 个版本的 clip_order + 文案包装
     - 每个版本标注 approach_tag（切入角度）
  → AI 质检（DeepSeek API，~10 秒）
     - 检查违规词、碎片化、叙事完整度
     - 不合格版本自动淘汰，保留合格版本
  → FFmpeg 剪辑（本地，CPU 模式 ~30 秒/版本）
     - 按 clip_order 拼接片段
     - 输出原速 + 1.25x 加速两个变体
  → UI 展示 3 个版本预览 + 文案
  → 用户点击「导出」
```

## 三、项目结构

```
CutPilot/                          # 新仓库，独立于 VideoFactory4
├── main.py                        # 入口
├── ui/
│   ├── main_window.py             # 主窗口布局
│   ├── drop_zone.py               # 拖拽导入组件
│   ├── result_panel.py            # 成品展示面板（预览+文案+标签）
│   ├── progress_widget.py         # 进度条组件
│   └── styles.py                  # QSS 样式
├── core/
│   ├── config.py                  # 配置（API Key、模型名等）
│   ├── models.py                  # 数据模型（Sentence, ScriptVersion）
│   ├── ai_client.py               # DeepSeek API 客户端
│   ├── asr.py                     # FunASR 本地语音识别
│   ├── director.py                # AI 编导（生成脚本版本）
│   ├── inspector.py               # AI 质检
│   ├── editor.py                  # FFmpeg 剪辑引擎
│   └── pipeline.py                # 编排整条管线
├── config/
│   ├── prompts/
│   │   ├── sentence_selector.md   # 编导 prompt
│   │   ├── inspector.md           # 质检 prompt（从 VF4 源码中提取）
│   │   └── categories/            # 品类专属 prompt
│   │       ├── wig.md
│   │       ├── makeup.md
│   │       ├── skincare.md
│   │       └── clothing.md
│   └── sensitive_words.json       # 违禁词/极限词名单（质检用）
├── assets/
│   ├── icon.ico                   # 应用图标
│   └── logo.png                   # 启动 Logo
├── build.py                       # PyInstaller 打包脚本
├── pyproject.toml                 # 依赖管理
├── requirements.txt               # pip 安装依赖
└── README.md                      # 用户使用说明
```

## 四、从 VF4 复用的模块

| VF4 源文件 | CutPilot 目标 | 改动 |
|-----------|-------------|------|
| `src/core/ai_client.py` | `core/ai_client.py` | 去掉 `src.core.config` 依赖，改用本地 config；`_MODEL` 改为从 config 传参 |
| `src/core/models.py` | `core/models.py` | 只保留 `Sentence`, `ScriptVersion`, `APPROACH_TAGS` |
| `src/script/writer.py` | `core/director.py` | 提取核心函数：`_load_prompt_template`, `_build_numbered_text`, `_call_llm`, `_extract_json`, `parse_json_versions`, `select_sentences` |
| `src/script/category_detector.py` | `core/category_detector.py` | 直接复用（纯关键词匹配，无外部依赖） |
| `src/agents/inspector.py` | `core/inspector.py` | 提取质检评分逻辑，去掉 Agent 框架依赖；将内联 `_INSPECTOR_PROMPT` 提取为 `config/prompts/inspector.md` |
| `src/synthesis/ffmpeg_cutter.py` | `core/editor.py` | 复用 `rough_cut()` 函数，新增 `cut_versions()` 桥接函数（见下方说明） |
| `src/parse/asr.py` | `core/asr.py` | 复用，去掉 NAS 临时文件逻辑；ASR 调用需包裹 `asyncio.to_thread()` 避免阻塞 UI |
| `config/prompts/sentence_selector.md` | `config/prompts/sentence_selector.md` | 直接复用 |
| `config/prompts/categories/*.md` | `config/prompts/categories/*.md` | 直接复用（wig, makeup, skincare, clothing） |
| `config/sensitive_words.json` | `config/sensitive_words.json` | 直接复用 |

### 砍掉的模块（CutPilot 不需要）

- Redis / FileVideoClient / 状态管理
- NAS 路径逻辑
- batch_run.py / vf.py / task_manifest
- 影刀 RPA 对接
- 飞书同步
- link_matcher（用户不需要匹配链接）
- publish.xlsx（界面直接展示文案）
- Agent 消息总线（BaseAgent, MessageBus）
- dispatch_to_packager / packaging_machine

## 五、UI 设计

### 主窗口布局

```
┌─ CutPilot — AI 副驾驶 ─────────────────────────────────────┐
│                                                             │
│  ┌─ 素材区 ──────────────┐  ┌─ 成品区 ──────────────────┐  │
│  │                        │  │                            │  │
│  │  📁 拖入视频到这里      │  │  ┌─ V1 [价格冲击] ───────┐ │  │
│  │     或点击选择文件      │  │  │ ▶ 视频预览缩略图       │ │  │
│  │                        │  │  │ 发布文案: 9.9元抢...   │ │  │
│  │  ─────────────────     │  │  │ 封面: 9.9抢购          │ │  │
│  │  已导入:               │  │  │ 标签: #好物 #平价      │ │  │
│  │  ✓ 产品A.mp4  3:21    │  │  │         [复制文案]      │ │  │
│  │  ⏳ 产品B.mp4  2:45    │  │  └────────────────────────┘ │  │
│  │  ○ 产品C.mp4  4:12    │  │                            │  │
│  │                        │  │  ┌─ V2 [使用场景] ───────┐ │  │
│  │  状态图标:             │  │  │ ...                    │ │  │
│  │  ✓ 已完成              │  │  └────────────────────────┘ │  │
│  │  ⏳ 处理中             │  │                            │  │
│  │  ○ 排队中              │  │  ┌─ V3 [外观颜值] ───────┐ │  │
│  │                        │  │  │ ...                    │ │  │
│  └────────────────────────┘  │  └────────────────────────┘ │  │
│                              └────────────────────────────┘  │
│  ┌─ 进度条 ──────────────────────────────────────────────┐  │
│  │  产品A: ████████████████░░░░ 80%  正在剪辑 V2...       │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                             │
│  [选择输出目录: D:\CutPilot_Output]    [一键生成]  [导出全部] │
└─────────────────────────────────────────────────────────────┘
```

### 交互流程

1. **导入**：拖拽 .mp4 文件到素材区（支持多文件），或点击选择
2. **处理**：点击「一键生成」，逐个处理，进度条实时更新
3. **预览**：处理完成后，成品区展示每个版本的缩略图 + 文案
4. **复制**：每个版本有「复制文案」按钮，一键复制发布文案+标题+标签
5. **导出**：点击「导出全部」，所有成品视频导出到指定目录

### 输出目录结构

```
D:\CutPilot_Output\
├── 产品A/
│   ├── 产品A_v1.mp4
│   ├── 产品A_v1_fast.mp4
│   ├── 产品A_v2.mp4
│   ├── 产品A_v2_fast.mp4
│   ├── 产品A_v3.mp4
│   ├── 产品A_v3_fast.mp4
│   └── 文案.txt              # 所有版本的文案、标题、标签汇总
└── 产品B/
    └── ...
```

`文案.txt` 格式：
```
=== V1 [价格冲击] ===
发布文案: 9.9元抢到手软...
封面主标题: 9.9抢购
封面副标题: 限时清仓
标签: #好物推荐 #平价好物 #9块9 #抖音好物 #性价比

=== V2 [使用场景] ===
...
```

## 六、配置文件

`core/config.py` — 简化版配置，无 Redis/NAS/飞书依赖：

```python
from pydantic_settings import BaseSettings

class CutPilotConfig(BaseSettings):
    model_config = {"env_prefix": "CUTPILOT_", "env_file": ".env", "frozen": True}

    # DeepSeek API
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "deepseek-v3"

    # 处理参数
    max_versions: int = 3          # 最多生成几个版本
    min_sentences: int = 15        # 少于此句数跳过
    generate_fast: bool = True     # 是否生成 1.25x 加速版

    # 输出
    output_dir: str = ""           # 默认输出目录
```

## 七、关键适配设计

### editor.py 桥接函数

VF4 的 `rough_cut()` 接受 `list[tuple[float, float]]` 时间段。CutPilot 的管线用 `ScriptVersion.sentence_ids` + `list[Sentence]`。需要新增桥接函数：

```python
async def cut_versions(
    video_path: Path,
    versions: list[ScriptVersion],
    sentences: list[Sentence],
    config: CutPilotConfig,
) -> list[dict]:
    """为每个版本调用 rough_cut，输出原速 + 1.25x 加速。"""
    sentence_map = {s.id: s for s in sentences}
    results = []
    for v in versions:
        time_spans = [
            (sentence_map[sid].start_sec, sentence_map[sid].end_sec)
            for sid in v.sentence_ids if sid in sentence_map
        ]
        # 原速
        out_path = output_dir / f"{stem}_v{v.version_id}.mp4"
        await rough_cut(str(video_path), time_spans, str(out_path))
        results.append({"version_id": v.version_id, "path": str(out_path), "speed": "1x"})
        # 1.25x 加速
        if config.generate_fast:
            fast_path = output_dir / f"{stem}_v{v.version_id}_fast.mp4"
            await rough_cut(str(video_path), time_spans, str(fast_path), speed=1.25)
            results.append({"version_id": v.version_id, "path": str(fast_path), "speed": "1.25x"})
    return results
```

### ASR 线程化

FunASR 的 `model.generate()` 是同步阻塞调用（~90 秒）。在 PySide6 GUI 中必须放到线程执行，避免 UI 冻结：

```python
# pipeline.py 中调用 ASR 时
segments = await asyncio.to_thread(asr.transcribe_video_sync, str(video_path))
```

### 中间结果缓存

ASR 结果缓存到磁盘（`{video_name}.asr.json`），如果 AI 调用失败需要重试时，跳过 ASR 步骤直接从缓存读取。

### FFmpeg 捆绑策略

在 `assets/ffmpeg/` 目录下预置 Windows 版 FFmpeg 静态构建（~80MB）。应用启动时检测：
1. 优先使用 `assets/ffmpeg/ffmpeg.exe`
2. 其次检测系统 PATH 中的 ffmpeg
3. 都没有则提示用户下载

## 八、核心管线 pipeline.py

```python
async def process_video(video_path: Path, config: CutPilotConfig,
                        on_progress: Callable = None) -> ProcessResult:
    """处理单个视频：ASR → 编导 → 质检 → 剪辑"""

    # 1. ASR 识别（线程化，避免阻塞 UI）
    #    优先从缓存读取（{video_name}.asr.json）
    if on_progress: on_progress("正在识别语音...", 10)
    segments = await asyncio.to_thread(asr.transcribe_video_sync, str(video_path))
    sentences = [Sentence(id=i+1, start_sec=s.start, end_sec=s.end, text=s.text)
                 for i, s in enumerate(segments)]
    _save_asr_cache(video_path, sentences)  # 缓存 ASR 结果

    if len(sentences) < config.min_sentences:
        return ProcessResult(success=False, error=f"素材太短（{len(sentences)}句，需要至少{config.min_sentences}句）")

    # 2. AI 编导
    if on_progress: on_progress("AI 正在生成脚本...", 40)
    versions = await director.generate_versions(sentences, config)

    # 3. AI 质检
    if on_progress: on_progress("AI 正在质检...", 60)
    approved = await inspector.review_versions(versions, sentences, config)

    if not approved:
        return ProcessResult(success=False, error="所有版本未通过质检")

    # 4. FFmpeg 剪辑
    if on_progress: on_progress("正在剪辑视频...", 75)
    output_files = await editor.cut_versions(
        video_path, approved, sentences, config
    )

    if on_progress: on_progress("完成", 100)
    return ProcessResult(
        success=True,
        versions=approved,
        output_files=output_files,
    )
```

## 八、打包分发

### PyInstaller 打包

```bash
pyinstaller --onedir --windowed --name CutPilot \
    --icon assets/icon.ico \
    --add-data "config/prompts:config/prompts" \
    --add-data "assets:assets" \
    main.py
```

### 依赖

```
PySide6>=6.6.0        # GUI
pydantic>=2.10.0       # 数据模型
pydantic-settings>=2.7.0
openai>=1.0.0          # DeepSeek API（OpenAI 兼容）
httpx>=0.28.0          # HTTP 客户端
funasr>=1.0.0          # ASR 语音识别
torch>=2.0.0           # FunASR 依赖（CPU 版本）
```

### 安装包体积估算

| 组件 | 大小 |
|------|------|
| PySide6 | ~80MB |
| PyTorch (CPU) | ~150MB |
| FunASR 模型 | ~400MB |
| FFmpeg | ~80MB (bundled) |
| 其他 | ~20MB |
| **总计** | **~730MB** |

首次启动时 FunASR 模型会自动下载（~400MB），后续无需重复下载。也可以预打包进安装包。

## 九、MVP 不做的事情

- 不做云端授权系统（手动发放 .env 文件配 API Key）
- 不做用户注册/登录
- 不做使用量统计/限额
- 不做自动更新
- 不做视频预览播放（只展示缩略图）
- 不做批量导入历史记录
- 不做 Mac 版（先 Windows）
- 不做国际化（先中文）

## 十、涉及文件总表

| 文件 | 动作 | 来源 |
|------|------|------|
| `main.py` | 新建 | 应用入口 |
| `ui/main_window.py` | 新建 | 主窗口 |
| `ui/drop_zone.py` | 新建 | 拖拽组件 |
| `ui/result_panel.py` | 新建 | 成品展示 |
| `ui/progress_widget.py` | 新建 | 进度条 |
| `ui/styles.py` | 新建 | 样式表 |
| `core/config.py` | 新建 | 配置（精简版） |
| `core/models.py` | 从 VF4 精简 | 只留 Sentence + ScriptVersion + APPROACH_TAGS |
| `core/ai_client.py` | 从 VF4 适配 | 去掉 Settings 依赖，model 从 config 传参 |
| `core/asr.py` | 从 VF4 适配 | 去掉 NAS 逻辑，同步函数包裹 asyncio.to_thread |
| `core/director.py` | 从 VF4 提取 | writer.py 核心函数 |
| `core/category_detector.py` | 从 VF4 复用 | 品类关键词检测（无外部依赖） |
| `core/inspector.py` | 从 VF4 提取 | 质检逻辑，prompt 提取为外部文件 |
| `core/editor.py` | 从 VF4 适配 | rough_cut + 新增 cut_versions 桥接函数 |
| `core/pipeline.py` | 新建 | 管线编排（含进度回调、ASR 缓存） |
| `config/prompts/sentence_selector.md` | 从 VF4 复制 | 编导 prompt |
| `config/prompts/inspector.md` | 从 VF4 源码提取 | 质检 prompt（原内联在 inspector.py 中） |
| `config/prompts/categories/*.md` | 从 VF4 复制 | 品类专属 prompt |
| `config/sensitive_words.json` | 从 VF4 复制 | 违禁词名单 |
| `assets/ffmpeg/` | 预置 | Windows FFmpeg 静态构建 |
| `build.py` | 新建 | PyInstaller 打包（含 PySide6/torch hooks） |
| `pyproject.toml` | 新建 | 依赖管理 |
