# AGENTS.md

本文档是 Sakura Desktop Pet 项目的 AI Agent 协作指引，同时作为 Claude Code 的项目级配置文件（替代 CLAUDE.md）。

---

## 1. 项目概述

**Sakura Desktop Pet** 是一个基于 Python/PySide6 的桌面 Agent / 桌宠项目。与传统等待用户输入的聊天机器人不同，Sakura 会主动观察屏幕内容并发起对话，支持角色扮演、工具调用、长期记忆和 TTS 语音。

- **入口文件**: `main.py`
- **主要源码**: `app/`
- **Python 版本**: >= 3.10
- **许可证**: MIT
- **仓库地址**: https://github.com/Rvosy/sakura

### 核心技术栈

| 技术 | 用途 |
|------|------|
| PySide6 >= 6.7 | Qt GUI 框架 |
| OpenAI 兼容 API | LLM 后端 |
| Qdrant >= 1.12.0 | 向量存储（长期记忆） |
| SQLAlchemy >= 2.0.31 | 记忆数据库 ORM |
| Sentence-Transformers | 本地嵌入模型 |
| Playwright >= 1.40 | 浏览器自动化（插件） |
| MCP >= 1.9 | 工具服务器协议 |
| PyYAML | 配置文件解析 |
| uv >= 0.7.0 | Python 包管理 |
| pytest | 测试框架 |

---

## 2. 目录结构速览

```
.
├── main.py                  # 应用入口
├── start.bat                # Windows 启动脚本
├── start_studio.bat         # 角色编辑器启动脚本
├── install.bat              # Windows 依赖安装脚本
├── requirements.txt         # 生产依赖
├── requirements-dev.txt     # 测试依赖
├── VERSION                  # 版本号文件
├── CHANGELOG.md             # 版本发布记录
│
├── app/                     # 【核心】应用源码
│   ├── agent/               #   Agent 决策层：Runtime、工具、记忆、屏幕感知、MCP
│   ├── backchannel/         #   本地快速接话（LLM 等待期间的即时回复）
│   ├── config/              #   配置管理：YAML 读写、迁移、角色加载
│   ├── core/                #   应用核心：启动装配、管线、自检、资源管理
│   ├── llm/                 #   LLM 客户端、回复解析、提示词模板
│   ├── plugins/             #   插件系统：发现、管理、事件、服务门面
│   ├── renderers/           #   可扩展角色渲染器
│   ├── storage/             #   存储层：路径、聊天历史、视觉观察
│   ├── ui/                  #   UI 组件：桌宠窗口、设置、历史、立绘、字幕
│   └── voice/               #   TTS 服务、合成、播放
│
├── plugins/                 # 本地插件实现（如 Playwright 浏览器插件）
├── characters/              # 角色包（.char 包：人格卡、立绘、语音权重）
├── data/                    # 运行时数据（config/、chat_history/、memory/）
├── tests/                   # pytest 测试
│   ├── unit/                #   单元测试
│   ├── integration/         #   集成测试
│   └── ui/                  #   UI 测试（Qt/PySide6）
├── docs/                    # 文档（技术 README、插件 SDK、安装指南）
├── tools/                   # 工具
│   ├── studio/              #   SakuraCharacterStudio（GUI 角色编辑器）
│   ├── mcp/                 #   MCP Server 运行时
│   └── cleanup.py           #   安全清理工具
├── scripts/                 # macOS/Linux Shell 脚本
├── third_party/             # 第三方代码（mem0 分支副本）
└── assets/                  # 静态资源（截图、接话素材）
```

---

## 3. 架构速览

### 启动流程

1. `main.py` 创建 `QApplication`，取得单实例锁
2. 生成缺失默认配置，执行版本化迁移
3. 自检：写权限、配置文件、磁盘空间、记忆库锁
4. `AppSettingsService` 加载 `data/config/*.yaml`
5. `CharacterRegistry` 扫描角色包
6. `bootstrap.py` 组装 `AppContext`、`ResourceManager`、工具、记忆、MCP、插件、TTS
7. 后台装配耗时服务，显示 `PetWindow`

### 核心运行时链路

```
PetWindow → ChatWorker (后台线程) → ChatPipeline (对话编排)
  → ContextOrchestrator (上下文预算 & 选择)
  → AgentRuntime (原生 tool_calls 循环)
  → ChatReply (分段 JSON：日文原文 + 中文字幕 + 语气 + 立绘标识)
  → UI 驱动字幕、立绘切换、TTS 播放
```

### 关键组件

| 组件 | 职责 |
|------|------|
| `AppContext` | 全局依赖容器，持有 `ResourceRegistry` 等共享服务 |
| `ResourceManager` | 统一管理线程/进程/服务/异步循环的生命周期、关闭顺序与跨线程投递。Qt wrapper 持有共享 `ResourceRegistry`，退出时按依赖顺序关闭所有托管资源 |
| `ResourceRegistry` | 纯 Python 线程安全的资源登记表，bootstrap 创建后注入 MemoryStore、PluginManager、MCP Provider 等服务 |
| `AgentRuntime` | 直接调用 OpenAI 兼容 API 的原生 `tool_calls` 循环，工具调用/结果只在运行时内部流转 |
| `ToolRegistry` | 统一工具注册（内置工具 + MCP 工具 + 插件工具），含权限策略 |
| `ContextOrchestrator` | 按优先级、信任级别和 token 预算选择上下文，组装 `ContextSnapshot` |
| `Backchannel` | LLM 等待期间提供本地快速接话，分类线程由 `ThreadGroupResource` 托管 |
| `Memory` | 分层长期记忆（核心信息 / 经历 / 任务 / 操作习惯），自动整理（curation）；Qdrant 向量存储 + Sentence-Transformers 本地嵌入 |
| `TTS` | GPT-SoVITS 语音合成与播放，已拆分为服务监管/合成队列/播放端点三个独立组件 |

### ResourceManager 线程域硬约束

Sakura 同时跨越三套对象生命周期（CPython GC / PySide Shiboken wrapper / Qt C++ QObject parent-child）。修改代码时必须遵守**线程域边界**：

| 必须留在 UI 主线程 | 可由后台资源托管 |
|---|---|
| `QWidget` / `QPixmap` / `QMediaPlayer` / `QAudioOutput` / Qt UI 定时器 | TTS HTTP 合成、本地 TTS 服务进程、模型加载、MCP bridge、memory preload、接话分类、截图编码 |

关闭链路收敛为：发关闭事件 → 取消 UI 流 → `resource_manager.stop_all()`。**不要**手写串联 TTS / MCP / plugin / renderer close。

### 上下文与 Token 预算

当前裁剪 (`app/llm/context_trimming.py`) 按**字符数**而非 token 数裁剪，且只统计对话消息——system 人格、工具定义、runtime_context 未纳入预算。`app/llm/prompts/runtime.py` 已有 token 估算函数（`estimate_prompt_tokens` / `truncate_to_token_budget`），`PromptInspection` 已逐段估算 system_prompt + runtime_context，但缺少全量 token 记账。

Prompt 真实组成为：`T(system_prompt) + T(tools_json) + T(conversation_messages) + T(runtime_context) + Σ image_cost`。设计文档：`docs/context-token-budget.md`。

### TTS 架构（已拆分）

TTS Provider 已从单个巨类拆为三个独立组件：

| 组件 | 文件 | 线程域 | 资源托管 |
|------|------|--------|----------|
| 服务进程监管 | `tts_service.py` | 子进程 + 合成线程内同步调用 | `ProcessResource` |
| 合成队列 | `tts_synthesis.py` | 独立 Python daemon 线程（HTTP 合成） | `ThreadResource` |
| 播放端点 | `tts_playback.py` | UI 主线程（Qt 信号/slot） | 不托管 |

协调器（`GPTSoVITSTTSProvider` / `GenieTTSProvider`）保持类名不变，为纯装配+委托。TTS 测试退出阶段的 native access violation 已有修复记录（`docs/TTS_SHUTDOWN_NATIVE_CRASH.md`）。

---

## 4. 常用命令

### 运行环境

- **Windows Release 包**: 使用 `runtime/python.exe`（bundled Python）
- **源码开发**: 任意 Python 3.10+ 虚拟环境均可
- macOS/Linux 参考 `scripts/` 目录下的 Shell 脚本

### 启动应用

```powershell
python main.py
```

Windows 用户可直接双击 `start.bat`。

### 运行测试

```powershell
# 全部测试（默认使用 Qt offscreen 模式）
python -m pytest

# 单元测试（快速，无外部依赖）
python -m pytest tests/unit

# 集成测试
python -m pytest tests/integration

# UI 测试
python -m pytest tests/ui

# 按标记筛选
python -m pytest -m unit
python -m pytest -m "not slow and not requires_llm"
python -m pytest -m "integration and not requires_network"
```

### pytest 标记

| 标记 | 说明 |
|------|------|
| `unit` | 快速单元测试 |
| `integration` | 集成测试 |
| `ui` | Qt/PySide6 UI 测试 |
| `slow` | 耗时较长的测试 |
| `requires_llm` | 需要真实 LLM/API 访问 |
| `requires_network` | 需要网络连接 |
| `requires_playwright` | 需要 Playwright/浏览器 |

### 运行特定测试

```powershell
# 特定文件
python -m pytest tests/unit/test_config.py

# 特定测试类/函数
python -m pytest tests/unit/test_config.py::TestSettingsService::test_load_yaml
```

---

## 5. 开发约定

### 代码风格

- 遵循现有代码的命名和注释风格
- 类型注解（type hints）用于公开 API 和核心模块
- 模块内部使用 logger 记录日志（`app/core/debug_log.py`）
- 中文注释和文档字符串在用户界面和业务逻辑中广泛使用

### 配置系统

- 所有用户配置位于 `data/config/*.yaml`
- `api.yaml` — API 密钥、模型、TTS 配置
- `system_config.yaml` — UI、屏幕感知、工具循环、回话、记忆整理等
- `characters.yaml` — 当前角色选择
- `app/config/settings_service.py` 负责读写
- `app/config/default_configs.py` 负责生成缺失项

### 角色包结构

- 角色包位于 `characters/` 目录
- 包含：`character.json`（人格卡）、立绘图片、TTS 语音权重
- `CharacterRegistry` 在启动时扫描并加载
- 角色编辑器：`start_studio.bat` 或 `python -m tools.studio`

### 插件开发

- 插件实现放 `plugins/`，系统代码放 `app/plugins/`
- 插件只通过 `app.plugins.*` 公开 API 接入，禁止直接访问 `PetWindow`、TTS provider 内部对象或全局 ResourceManager
- 插件通过 `PluginServices` 门面请求 UI / TTS / Agent 行为，通过 `context.events` 订阅宿主事件
- 动态上下文注入用 `ContextProviderContribution`（每次请求动态生成），静态提示词修改用 `PromptPatchContribution`
- 插件 API 版本当前为 `1`，向前兼容：同一 api_version 内只做扩展不做破坏性修改
- 详见 `docs/SAKURA_PLUGIN_SDK.md`

### ResourceManager 约束

- `QWidget` / `QPixmap` / `QMediaPlayer` / `QAudioOutput` / Qt UI 定时器**必须留在 UI 主线程**
- 新增后台服务需通过 `ResourceRegistry` 登记，由 `ResourceManager` 统一管理生命周期
- `PetWindow.close_external_tools()` 已收敛为纯事件+`stop_all()`，不要在其中手写资源关闭串联
- `MemoryStore.close()` 必须先失效 generation → 停登记线程 → 关闭 runtime（顺序不可变）

### 日志

- 调试日志默认关闭，通过 `system_config.yaml` 的 `debug.enabled` 开启
- 日志自动脱敏（API Key 等敏感信息不会写入日志）

---

## 6. Git 工作流

### Commit 类型

使用常规 commit 类型，保持简洁：

| 类型 | 用途 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | 缺陷修复 |
| `refactor:` | 代码重构 |
| `perf:` | 性能优化 |
| `style:` | 代码格式调整 |
| `docs:` | 文档更新 |
| `test:` | 测试相关 |
| `chore:` | 构建、依赖、版本号等杂项 |

### 分支策略

- `main` 为主分支
- 功能开发在独立分支进行
- 通过 Pull Request 合并

### 注意事项

- 版本号记录在 `VERSION` 文件中
- 版本发布后更新 `CHANGELOG.md`

---

## 7. AI Agent 行为约束

在 Sakura 仓库内工作时，AI Agent 必须遵守以下约束：

### Git 安全
- **禁止**主动执行 `git reset --hard`、`git checkout --`、`git clean -fd` 等破坏性命令，除非用户明确要求
- **禁止**还原用户已有的未提交改动
- 不主动 force push 或修改 git 历史

### 文件修改范围
- 只修改完成当前任务**必需**的文件
- 不做"顺手"的额外重构或格式化，除非任务明确包含
- 修改 `third_party/` 或 `tools/mcp/` 中的第三方代码前，确认确实属于当前任务范围

### 操作谨慎原则
- 二进制文件、角色资源（`characters/`）、运行时缓存（`runtime/`、`data/`）操作前格外谨慎
- 大文件或大型目录的批量操作前，先确认影响范围
- 删除文件前明确告知用户

### 测试验证
- Python 代码修改后，优先运行与改动范围最相关的 pytest
- 若改动影响核心链路（Agent 运行时、工具调用、配置加载、插件系统、TTS、UI、存储），扩大测试范围
- 若无法运行测试（缺少运行时环境、需要 LLM API 等），在最终回复中说明原因和未验证风险

### 依赖管理
- 添加新的 Python 依赖前确认必要性
- 新依赖需同步更新 `requirements.txt`（生产依赖）或 `requirements-dev.txt`（测试依赖）

---

## 8. 关键注意事项

### 路径限制
- **PySide6 在包含非 ASCII 字符的路径下会崩溃**（如中文路径）
- 项目必须放在纯英文路径下（例如 `D:\sakura`，而非 `D:\桌宠\sakura`）
- `start.bat` 启动时会自动检测此问题

### Python 环境
- Windows Release 包自带 `runtime/python.exe`，是本文档中 `python` 所指的解释器
- 源码开发时可使用任意 Python 3.10+ 虚拟环境
- `.python-version` 文件固定为 `3.10`

### TTS 语音
- 默认关闭，需在设置窗口中手动启用
- 依赖本地 GPT-SoVITS API（`http://127.0.0.1:9880/tts`）
- Windows 用户可在设置窗口一键下载整合包

### 记忆系统
- 使用 Qdrant 向量数据库
- 嵌入模型通过 Sentence-Transformers 本地运行
- HuggingFace 缓存目录：`runtime/hf-cache/`
- 记忆整理（curation）默认开启，由 `memory_curator.py` 自动管理

### MCP 工具
- 默认关闭，需在 `system_config.yaml` 中设置 `mcp.windows_enabled: true`
- MCP 运行时位于 `tools/mcp/`

### 屏幕感知
- 默认开启，每 20 分钟检查一次屏幕
- 发言冷却 10 分钟
- 可在 `system_config.yaml` 的 `screen_awareness` 节中调整

### 测试环境
- Qt 测试使用 `offscreen` 平台（无头模式），无需显示器
- 需要网络或 LLM 的测试默认不会在 CI 中运行（通过 pytest marker 隔离）
- **已知问题**：UI 测试退出阶段约 1/3 概率发生 native access violation（`0xC0000005`），为 PySide6 退出竞态的既存问题，非测试代码缺陷。重跑即可，以非崩溃运行是否全绿为准。详见 `docs/TTS_SHUTDOWN_NATIVE_CRASH.md`
- 组合测试时用 `--ignore` 排除缺少 `qtbot` 的分片（如 `tests/ui/test_history_window.py`）
- Windows 用 `./runtime/python.exe` 运行测试，不要用系统 Python（Anaconda 的 PySide6 可能崩 0xc0000139）

### macOS 开发注意
- 项目基于 PySide6（Qt），本身跨平台，可在 macOS 从源码运行
- Apple Silicon（`arm64`）可直接 `pip install -r requirements.txt`
- Rosetta（`x86_64`）需额外套用 `requirements-macos-intel.txt`（锁定 `numpy<2`），否则长期记忆功能失效
- python.org 版 Python 需手动安装 SSL 证书：`/Applications/Python 3.12/Install Certificates.command`
- macOS 自带的 `unzip` 会弄乱角色包中的 UTF-8 文件名，需用 Python `zipfile` 解压并修正编码
- `windows` MCP 服务器仅 Windows 可用，macOS 上保持关闭
- 详见 `docs/MACOS_SETUP.md`

---

## 9. 文档索引

### 用户文档

| 文档 | 内容 |
|------|------|
| `README.md` | 项目主 README（中文），面向最终用户 |
| `docs/README.en.md` | 英文 README |
| `docs/README.zh.md` | 中文 README 兼容重定向 |
| `docs/SETUP.md` | 安装与配置指南（Windows/macOS/Linux） |
| `docs/API_CONFIG.md` | API 配置教程（中转站 + 模型选择） |
| `docs/MACOS_SETUP.md` | macOS 专项：架构/Rosetta/SSL/TTS/角色包解压 |
| `CHANGELOG.md` | 版本发布记录 |
| `VERSION` | 当前版本号 |

### 技术文档

| 文档 | 内容 |
|------|------|
| `docs/TECHNICAL_README.md` | 架构深度讲解、配置项大全、TTS 技术配置、启动流程图 |
| `docs/SAKURA_PLUGIN_SDK.md` | 插件开发 SDK：工具注册、事件总线、上下文注入、渲染器后端、服务门面 |
| `docs/context-token-budget.md` | 上下文构成分析 & Token 预算设计（设计/参考文档，非已落地实现） |
| `docs/DESKTOP_PET_EXPERIENCE_ARCHITECTURE_PLAN.md` | 桌宠体验架构改造计划（Context Orchestrator / 会话延续 / 主动互动决策器） |

### 设计 & 实施记录

| 文档 | 内容 |
|------|------|
| `docs/RUNTIME_RESOURCE_MANAGER_PLAN.md` | ResourceManager 目标架构、资源状态机、线程域与关闭顺序（issue #94） |
| `docs/RESOURCE_MANAGER_HANDOFF.md` | ResourceManager 第 1-5 阶段完成交接文档（含验证命令和约束） |
| `docs/RESOURCE_MANAGER_PHASE_4_5_PLAN.md` | 第 4 & 5 阶段实施计划：接话资源化 / memory·MCP·plugin 统一治理 |
| `docs/RESOURCE_MANAGER_PHASE_4_PROMPT.md` | 第 4 阶段启动提示词（供新会话复制使用） |
| `docs/TTS_PROVIDER_SPLIT_PLAN.md` | 第 3 阶段实施计划：TTS Provider 拆分为服务/合成/播放三组件 |
| `docs/TTS_SHUTDOWN_NATIVE_CRASH.md` | TTS 退出竞态与 pytest Qt 清理 native crash 的归因与修复记录 |
| `docs/releases/PR_MAIN_0.9.8.md` | 0.9.8 版本 PR 描述 |
| `docs/releases/RELEASE_0.9.8.md` | 0.9.8 版本发布说明 |
