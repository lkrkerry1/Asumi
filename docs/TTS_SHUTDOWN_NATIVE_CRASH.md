# 已知问题：pytest 退出阶段 native access violation（待修复）

> 一个**本地 runtime 的计时性 native 崩溃**，与 issue #94 重构无关（重构前就存在）。
> 记录于此供后续单独修复。不影响功能正确性：非崩溃运行下全部测试通过。

## 现象
跑 `tests/ui`（或 `tests/unit tests/ui` 组合）时，**约 1/3 概率**在进程退出阶段报：

```
Windows fatal exception: access violation

Current thread 0x........ (most recent call first):
  <无 Python 帧，或停在 pytest 退出栈>
```

特征：
- **不伴随任何具体测试 FAIL**——崩溃发生在所有测试跑完、解释器退出阶段。
- 非崩溃的那次运行**全绿**：`tests/ui` = 283 passed，`tests/unit + tests/ui` = 988 passed。
- `-v`（verbose）模式有时能跑到打印 `283 passed` 再崩或不崩——纯计时性，非确定性。

## 复现
```bash
cd C:/Users/LBW/MyFile/sakura-project/Sakura
for i in 1 2 3; do
  ./runtime/python.exe -m pytest tests/ui -q -p no:warnings \
    --deselect tests/ui/test_history_window.py 2>&1 \
    | grep -iE "Windows fatal|passed" | head -1
done
# 约 1/3 的 run 打印 "Windows fatal exception: access violation"
```

## 证据：早于第 3 阶段就存在（非本次回归）
用 `git stash` 把工作树回退到 **commit 4（`f6c70d4`，TTS 播放端点拆分之前）**，跑 `tests/ui` 4 次：

```
run 1: ....Windows fatal exception: access violation
run 2: ................................Windows fatal exception: access violation
run 3: 283 passed
run 4: 283 passed
```

即播放端点拆分前**同样以相近频率复现**。第 3 阶段（含播放端点 QObject 拆分）未引入也未加重它。

## 根因假设
Sakura 的 TTS 合成用「**每请求一个一次性 daemon 线程**」在后台 `emit` Qt 信号回 UI 线程的
QObject（`TTSPlaybackEndpoint` 的 `_audio_ready`/`_failed` 等）。许多 `tests/ui` / `tests/unit`
测试创建真实 `GPTSoVITSTTSProvider` 并触发 `speak`/`prepare`，spawn 的 daemon 线程会去连不存在的
本地服务、随后 `emit` 失败信号。若测试结束、QApplication/event loop 与 Qt C++ 对象在解释器退出阶段
被销毁，而 daemon 线程仍在 `emit`（或仍有 queued event 指向已释放对象），Shiboken 触及已释放的
C++ QObject → access violation。

这是 daemon-thread-emits-to-QObject 模式在**解释器退出**时的固有竞态，跨 issue #94 整段都存在。
设计文档（`RUNTIME_RESOURCE_MANAGER_PLAN.md`）的 wrapper-retention / lingering 机制是为运行期的
double-destruction 设计的，**退出期的这条路径未被覆盖**。

## 修复方向（候选，未验证）
- **测试侧**：给创建真实 provider 的测试加 fixture，在 teardown 里 `provider.close()` +
  等合成线程收敛（`ThreadResource.stop` join/lingering）后再让 QApplication 退出；或
  `conftest.py` 的 `_cleanup_qt_objects` 增加「等所有受管 daemon 线程 emit 完成 / 断开信号」步骤。
- **产品侧**：合成线程在 `emit` 前用 `shiboken6.isValid(sink)` 校验端点存活；或 provider/endpoint
  在关闭时先 `disconnect()` 全部信号、并设置「不再 emit」哨兵，让在飞 daemon 线程的 emit 变为 no-op。
- **退出顺序**：确保 `QApplication` 析构前，所有受管线程（含 daemon）已被 `stop_all` 收敛或显式
  断开与 Qt 对象的连接（可在 RM 增「退出前 quiesce」入口）。

## 影响与现状处置
- **不影响功能**：仅退出期崩溃，不改变任何测试断言结果。
- CI 不出现（与 `test_history_window`/`sdk` 一样属本地环境/计时问题）。
- 当前处置：**重跑即可**，以「非崩溃运行是否全绿」为准。后续作为独立任务修复。
