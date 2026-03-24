# CutPilot MVP Implementation Plan

**Date**: 2026-03-24
**Status**: Draft — pending user approval
**Goal**: 实现完整管线，交付可打包的 MVP 桌面产品

---

## 一、当前状态

### 已完成
- UI 框架（暗色主题、拖拽导入、成品版本卡片、进度条）
- `core/config.py` — pydantic-settings 配置
- `core/models.py` — Sentence, ScriptVersion, ProcessResult
- `core/ai_client.py` — DeepSeek API 客户端
- `core/asr.py` — FunASR 本地 + HTTP fallback
- `core/category_detector.py` — 品类关键词检测
- 编导 prompt + 4 个品类 prompt + 违禁词名单

### 待实现（本次计划范围）
- `core/director.py` — AI 编导
- `core/inspector.py` — AI 质检
- `core/editor.py` — FFmpeg 剪辑
- `core/cache_manager.py` — 统一缓存
- `core/pipeline.py` — 管线编排
- UI ↔ Pipeline 对接（QThread Worker）
- 增强项：热词 ASR、prompt 升级、DeliveryCard 输出
- 测试 + PyInstaller 打包

---

## 二、架构决策

### 从调研报告中吸收的能力（融入 MVP，不增加独立模块）

| 能力 | 实现方式 | 理由 |
|------|---------|------|
| 脚本策略引擎 | 写进 prompt（不做 strategy.py） | LLM 一次调用已包含策略选择 |
| Hook 生成 | 写进 prompt（不做 hook_generator.py） | 编导 prompt 已输出 cover_title/hook |
| 候选评分 | inspector.py 内置（不做 scorer.py） | 质检本身就是评分筛选 |
| 包装输出 | 扩展 ScriptVersion 字段 | 不需要独立 packager.py |
| 热词增强 | asr.py 加 hotword 参数 | FunASR 原生支持，一行代码 |
| 缓存/恢复 | 新增 cache_manager.py | 管线各步骤缓存，失败可恢复 |
| DeliveryCard | 扩展 models.py | 增加 hook_text, why_it_may_work 等字段 |

### 不做的事（推迟到 v0.2+）
- 说话人识别（额外模型 ~200MB）
- Word-level timestamps（需换 ASR 输出格式）
- 场景检测（需 PySceneDetect 依赖）
- 9:16 竖版重构（需人脸检测模型）
- Hook overlay 烧录（需 FFmpeg drawtext 链）
- SRT 字幕导出（数据已有，纯工程活）

---

## 三、模块依赖关系

```
独立模块（可并行开发）:
  ├── core/director.py      ← 提取自 VF3 writer.py
  ├── core/inspector.py     ← 提取自 VF3 reviewer.py
  ├── core/editor.py        ← 提取自 VF3 ffmpeg_cutter.py
  └── core/cache_manager.py ← 新建

依赖模块（串行）:
  └── core/pipeline.py      ← 依赖上述 4 个模块
      └── ui/worker.py      ← 依赖 pipeline.py
          └── UI 对接       ← 依赖 worker.py

增强项（可与独立模块并行）:
  ├── models.py 扩展        ← DeliveryCard 字段
  ├── asr.py 热词增强       ← hotword 参数
  ├── prompt 升级           ← 融入策略/Hook/包装思想
  └── inspector prompt      ← 新建 config/prompts/inspector.md
```

---

## 四、执行阶段

### Phase 1: 并行构建独立模块（4 个 Agent 同时工作）

每个 Agent 在独立 worktree 中工作，完成后合并到 master。

#### Agent A: `core/director.py`
**来源**: VF3 `src/script/writer.py`
**提取函数**:
- `_load_prompt_template()` — 加载 prompt 模板
- `_build_numbered_text()` — 构建编号字幕文本
- `_extract_json()` — 解析 JSON（去 markdown fence）
- `parse_json_versions()` — 解析 AI 响应为 ScriptVersion
- `compute_version_duration()` — 计算版本时长
- `select_sentences()` → 重命名为 `generate_versions()`

**适配改动**:
- `from src.core.ai_client` → `from core.ai_client`
- model 参数从 config 传入，不硬编码
- 品类 prompt 加载（结合 category_detector 结果）
- 返回类型适配 CutPilot 的 ScriptVersion（含 publish_text/tags 等）

#### Agent B: `core/inspector.py` + `config/prompts/inspector.md`
**来源**: VF3 `src/script/reviewer.py`
**提取函数**:
- `load_sensitive_words()` — 违禁词加载
- `check_prohibited_words()` — 违禁词扫描
- `compute_overlap_ratio()` / `compute_overlap_matrix()` — 重叠检测
- `detect_overlap_groups()` — 重叠分组
- `extract_core_hook_text()` — Hook 文本提取
- `review_versions()` — 主审核函数（简化版，去掉 ReviewReport 复杂结构）

**适配改动**:
- 去掉 ReviewReport/PlanReview/ReviewDimensions（简化为返回 approved 的 ScriptVersion 列表）
- 审核 prompt 提取为 `config/prompts/inspector.md`
- AI 调用改用 CutPilot 的 `call_ai()`
- 去掉 ArrangementPlan 相关的 legacy 代码

#### Agent C: `core/editor.py`
**来源**: VF3 `src/synthesis/ffmpeg_cutter.py`
**提取函数**:
- `rough_cut()` — 核心剪辑（MoviePy 子片段 + 拼接）
- `_moviepy_cut_and_concat()` — 同步剪辑实现
- `_validate_output()` — ffprobe 验证
- 辅助函数: `_with_suffix()`, `_run_ffmpeg()`, `_escape_filtergraph_path()`

**新增函数**:
- `cut_versions()` — 桥接函数（ScriptVersion + Sentence → time_spans → rough_cut）
- 1.25x 加速变体生成（FFmpeg `-filter:v setpts=0.8*PTS -filter:a atempo=1.25`）

**适配改动**:
- 去掉 `ArrangementPlan`/`Segment` 依赖
- 输出路径按 CutPilot 规范（`{product}_v{n}.mp4` / `{product}_v{n}_fast.mp4`）
- `moviepy` 加入 `pyproject.toml` 依赖

#### Agent D: `core/cache_manager.py` + `models.py` 扩展 + ASR 热词 + prompt 升级
**新建**: `core/cache_manager.py`
```python
class CacheManager:
    def __init__(self, base_dir: Path): ...
    def cache_key(self, video_path: Path, stage: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def load(self, key: str) -> dict: ...
    def save(self, key: str, data: dict) -> None: ...
    def clear(self, video_path: Path) -> None: ...
```

**models.py 扩展**:
- `Sentence` 增加 `speaker_id: str | None = None`, `confidence: float | None = None`
- `ScriptVersion` 增加 `hook_text: str = ""`, `why_it_may_work: str = ""`
- 新增 `PipelineState` 模型（缓存状态跟踪）

**asr.py 热词增强**:
- `_get_local_model()` 接受 `hotwords: str` 参数
- 传入 FunASR `model.generate(hotword=hotwords_str)`

**prompt 升级**:
- `sentence_selector.md` 中融入策略思想（format_type 要求）
- 要求 AI 在返回 JSON 中包含 `hook_text` 和 `why_it_may_work` 字段

### Phase 2: 管线编排（串行，依赖 Phase 1）

#### `core/pipeline.py`
- `process_video()` — 主编排函数
- ASR → 品类检测 → 编导 → 质检 → 剪辑
- 每步使用 CacheManager 缓存结果
- 进度回调 `on_progress(stage: str, percent: int)`
- 错误处理 + 部分失败容忍

### Phase 3: UI 对接（串行，依赖 Phase 2）

#### `ui/worker.py` — QThread Worker
- `PipelineWorker(QThread)` — 后台处理线程
- Signal: `progress(str, int)`, `finished(ProcessResult)`, `error(str)`
- 逐个处理视频，通过 Signal 更新 UI

#### `ui/main_window.py` 对接
- 连接 Worker 的 Signal → 进度条/状态栏/成品面板
- 处理完成后启用导出按钮
- 导出逻辑：复制成品到用户选择的目录 + 生成文案.txt

### Phase 4: 测试 + 打包

#### 测试
- `tests/test_director.py` — mock AI 响应，验证 JSON 解析
- `tests/test_inspector.py` — 违禁词检测、重叠计算、审核流程
- `tests/test_editor.py` — mock moviepy/ffmpeg，验证路径生成
- `tests/test_cache_manager.py` — 缓存 CRUD
- `tests/test_pipeline.py` — 集成测试（mock 所有外部调用）

#### 打包
- `build.py` — PyInstaller 配置
- FFmpeg 捆绑策略
- 首次运行 FunASR 模型下载提示

---

## 五、执行策略

### 推荐方案：并行 Agent + Worktree 隔离

```
┌─────────────────────────────────────────────────┐
│ Phase 1: 4 个 Agent 并行（各自独立 worktree）    │
│                                                   │
│  Agent A ──→ director.py      ─┐                 │
│  Agent B ──→ inspector.py     ─┼─→ 合并到 master │
│  Agent C ──→ editor.py        ─┤                 │
│  Agent D ──→ cache + models   ─┘                 │
│                                                   │
│ 预计耗时：~15-20 分钟（并行）                     │
├─────────────────────────────────────────────────┤
│ Phase 2: pipeline.py（主线程，依赖合并结果）      │
│ 预计耗时：~10 分钟                                │
├─────────────────────────────────────────────────┤
│ Phase 3: UI 对接 + Worker                        │
│ 预计耗时：~10 分钟                                │
├─────────────────────────────────────────────────┤
│ Phase 4: 测试 + 打包配置                         │
│ 预计耗时：~15 分钟                                │
└─────────────────────────────────────────────────┘
```

### 为什么不用 "Teams" 模式
- 当前 Claude Code 的并行 Agent + worktree 已经提供了等效能力
- 每个 Agent 有独立上下文、独立 git 分支、互不干扰
- 完成后自动返回结果，由主线程合并
- 如果未来 Teams 模式提供更好的协调机制，可以无缝切换

---

## 六、文件变更总表

| 文件 | 动作 | Phase |
|------|------|-------|
| `core/director.py` | 新建（从 VF3 提取） | 1 |
| `core/inspector.py` | 新建（从 VF3 提取） | 1 |
| `core/editor.py` | 新建（从 VF3 提取） | 1 |
| `core/cache_manager.py` | 新建 | 1 |
| `core/models.py` | 修改（扩展字段） | 1 |
| `core/asr.py` | 修改（热词支持） | 1 |
| `config/prompts/sentence_selector.md` | 修改（策略增强） | 1 |
| `config/prompts/inspector.md` | 新建（质检 prompt） | 1 |
| `core/pipeline.py` | 新建 | 2 |
| `ui/worker.py` | 新建 | 3 |
| `ui/main_window.py` | 修改（对接 Worker） | 3 |
| `ui/result_panel.py` | 修改（展示新字段） | 3 |
| `pyproject.toml` | 修改（加 moviepy 依赖） | 1 |
| `tests/` | 新建（全部测试文件） | 4 |
| `build.py` | 新建 | 4 |

---

## 七、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| VF3 用 MoviePy，CutPilot 设计文档写 FFmpeg | 保留 MoviePy 方案（已验证），FFmpeg 作为 fallback |
| FunASR hotword API 可能版本不兼容 | 热词增强做 try/except，fallback 到无热词模式 |
| 并行 worktree 合并冲突 | Agent D 改 models.py，其他 Agent 只新建文件，冲突极小 |
| DeepSeek API 响应格式不稳定 | 复用 VF3 已验证的 JSON 解析逻辑 + 重试 |
| PyInstaller 打包 PySide6 + torch 体积大 | MVP 先不打包 torch，要求用户预装 Python 环境 |
