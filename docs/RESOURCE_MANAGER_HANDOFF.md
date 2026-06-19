# 交接：Sakura issue #94 资源管理器重构（第 3 阶段起）

> 给下一个会话的上下文交接。配合 `docs/RUNTIME_RESOURCE_MANAGER_PLAN.md`（设计文档）一起读。

## 项目与分支
- 仓库根目录：`C:\Users\LBW\MyFile\sakura-project\Sakura`（PySide6/Qt 桌宠，Windows）
- 当前分支：`refactor/resource-manager`（从 `origin/dev` 切出），第 1+2+3 阶段已完成，**未推送**。
- issue #94：把散落在 `PetWindow`（6700+ 行）里的 Qt/Python/进程生命周期，分 5 阶段抽到统一的后端资源管理器。

## 已完成（第 1+2 阶段，4 个提交）
1. 设计文档 `docs/RUNTIME_RESOURCE_MANAGER_PLAN.md`
2. 新增 `app/core/resource_manager.py`：
   - `QtWorkerResource`：托管一对 `QThread+QObject worker`；`stop()` 复刻 `cancel→requestInterruption→quit→wait→linger`；`_finalize()` 负责 wrapper 保留 + deleteLater + 清空宿主属性 + 调 `on_finished` 业务回调。
   - `ResourceManager(QObject)`：`spawn_qt_worker(...)` 工厂、`stop_all()`、`stop_qt_thread()` 原语、`retain_wrappers()`/prune、lingering 线程管理。`spawn_qt_worker` 有 `register=False` 选项（不纳入 `stop_all` 清单）。
   - 单测 `tests/unit/test_resource_manager.py`（10 个，全绿）。
3. 第 1 阶段：`PetWindow.__init__` 建 `self.resource_manager = ResourceManager(self)`；`_shutdown_qthread`/lingering/wrapper 委托给管理器。
4. 第 2 阶段：**7 个** QThread worker 创建点全部迁到 `spawn_qt_worker`（ChatWorker 聊天+动作、EventWorker、MemoryCurationWorker、ScreenObservationEncodeWorker、TTSReadyWarmupWorker、DeferredStartupWorker、TTSBundleMigrationWorker[用 register=False]）；`close_external_tools` 改用 `stop_all`；删了 `_shutdown_qthread` 和两个空 cleanup 方法，cleanup 方法只剩业务逻辑。

## 必须保持的约束
- 关闭序列、Shiboken wrapper 保留窗口、QThread 仍 parent 到窗口（否则 `tests/conftest.py:_cleanup_qt_objects` 靠 `children()` 递归回收不到线程）。
- `PetWindow` 仍持有 `self.worker`/`self.worker_thread` 等属性（指向管理器创建的对象），不要打断现有处理器与测试断言。
- 插件只能经 service facade，不得接触 PetWindow/TTS 内部实例。

## 测试怎么跑（重要）
- **用 `./runtime/python.exe -m pytest ...`**，不要用系统 Python（Anaconda 的 PySide6 会崩 0xc0000139）。
- 已知 2 个**环境性**失败、与重构无关：`tests/ui/test_history_window.py` 需要 qtbot（runtime 没装 pytest-qt）；`test_public_api_cleanup.py::test_legacy_sdk_package_is_removed` 因工作树里有残留未跟踪的 `sdk/` 目录。CI 下不会出现。
- 回归验证命令：`./runtime/python.exe -m pytest tests/unit/test_resource_manager.py tests/ui/test_pet_window.py tests/ui/test_backchannel_controller.py -q -p no:warnings`

## 第 3 阶段——拆分 TTS Provider（已完成）
原 `app/voice/tts.py` 的 `GPTSoVITSTTSProvider`（QObject）混的三类职责已拆分（详见
`docs/TTS_PROVIDER_SPLIT_PLAN.md` §8 完成记录），落地为 6 个提交：
- `app/voice/tts_types.py`：共享类型（`TTSPreparedAudio`/`_TTSRequest`/`TTSServiceState` 等）
- `app/voice/tts_service.py`：`TTSServiceSupervisor`(+`GenieServiceSupervisor`)——本地子进程
  探测/启动/接管/Broken pipe 重启/权重·模型加载；子进程经 `ProcessResource` 托管
- `app/voice/tts_synthesis.py`：`TTSSynthesisQueue` + `GPTSoVITSSynthesisEngine`/
  `GenieSynthesisEngine`——合成线程经 `ThreadResource` 托管
- `app/voice/tts_playback.py`：`TTSPlaybackEndpoint`（UI 主线程子 QObject，随协调器 moveToThread）
- `app/voice/tts.py`：瘦身为「装配 + 委托」协调器 + `NullTTSProvider` + `TTSProvider` 协议；
  `GenieTTSProvider` 不再有继承覆写，差异由 `settings.provider` 在协调器内选型；
  `close()` 走协调器自持 `ResourceManager.stop_all`
- `ResourceManager` 增 `ThreadResource`/`ProcessResource`/`ResourceState` 与泛化注册表

已保留的语义：prepare、播放完成回调、fallback timeout、Broken pipe 重启、临时 wav 清理、
soft-fail 静默跳过、`detach_local_service` 保留进程、provider 退役热切换。后台只生成 wav，
播放仍回 UI 线程。

## 下一步：第 4/5 阶段
按 `docs/RUNTIME_RESOURCE_MANAGER_PLAN.md` 继续把 ServiceResource（MCP / Plugin / Memory）
等纳入资源管理器。

## 工作方式（请遵守）
- **分段提交 git**，每个提交保持测试绿（破坏某测试就在同一提交里改它）。
- 用中文交流。
- 工作树里两个未跟踪的 `docs/*CHANGELOG.md` 与本次无关，别动。
- 测试：`./runtime/python.exe -m pytest`；tests/ui 退出阶段约 1/3 概率的 native access
  violation 是早于本阶段就存在的 daemon 线程/Qt 析构竞态，重跑即可，关注非崩溃运行是否全绿。
