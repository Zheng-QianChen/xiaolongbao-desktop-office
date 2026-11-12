# DeepSeekHarness（DSH）接入

本文说明 `desktop-pet/integrations/dsh/wang-bun.mjs` 的适配合同、虚构事件自检、真实宿主接线步骤和验收判定。

## 当前状态

- **已完成**：DSH 会话事件适配、只读元数据投影、基于虚构事件的适配自检。
- **尚未完成**：真实 DSH 宿主加载与真实会话联调。该验证是后续独立待办；在这份文档和 PR 中都不把“适配自检通过”写成“联调完成”。
- 自检不需要启动 DSH、WangBun、桥服务或网络，也不会读取真实会话。

## 数据流

```
DSH session/event(session, event)
  -> wang-bun.mjs project() 只投影任务元数据
  -> <runtime>/inbox/<20位时间戳>-<uuid>.json（原子 rename，先写 .tmp）
  -> bridge.py drain_spool() 校验并写入本机 SQLite
  -> 桌宠按 task 状态绘制工位
```

`runtime` 指向 WangBun 桥的数据目录，插件在其下创建 `inbox/`。插件只写这一份 JSON 文件，不发起网络请求，也不改变 DSH 会话状态。

## 事件合同

DSH 在每个已提交会话事件后发出 `session/event`（`@deepseek-ai/dsh-session` 的 `Context` 事件声明）。适配器只读取以下字段，其余字段一律不投影：

| DSH 字段 | 用途 | 约束 |
| --- | --- | --- |
| `session.id` | `thread_id`、标签前缀、事件 ID | 非空字符串 |
| `event.seq` | 事件 ID、去重身份 | 由 DSH 递增分配 |
| `event.time` | `observed_at`（毫秒转秒） | 有限数字；缺失时不写该字段 |
| `event.type` | `turn/start`、`turn/end` | 其他类型忽略 |
| `event.data.turn` | `run_id`（字符串化） | 整数 |
| `event.data.reason.kind` | `turn/end` 的收工状态 | 见下表 |

`turn/end` 状态映射：

| `reason.kind` | 桌宠 `kind` | 含义 |
| --- | --- | --- |
| `completed` | `completed` | 本轮完成 |
| `aborted` | `cancelled` | 用户/上级取消 |
| `interrupted` | `cancelled` | 崩溃后补写的收尾 |
| `error` | `failed` | 本轮失败 |
| `max-tokens` | `failed` | 达到输出上限 |
| `blocked` | `waiting` | 本轮被拦截，等待处理 |
| `forked` | 不投影 | 仅 fork 种子历史，不是实时事件 |
| 未知/缺失 | 不投影 | 前向兼容：新语义不会误报状态 |

写入磁盘的记录固定为：

```json
{
  "event_id": "<sha256(session.id, seq, type)>",
  "source": "dsh",
  "thread_id": "<session.id>",
  "run_id": "3",
  "kind": "started",
  "label": "DeepSeekHarness · session-",
  "managed": true,
  "observed_at": 1760000000.123
}
```

- `event_id` 对同一 `(session.id, seq, type)` 稳定；桥按 `[source, event_id]` 去重，重复投递不会生成第二个任务。
- `observed_at` 单位是秒，供桥判断过期事件；它不是文件时间戳。
- 记录不含用户提示词、助手回复、工具参数或工具输出。自检会显式检查这些内容不出现。
- 插件只观察 `turn/start`/`turn/end`，不发送心跳或 `disconnected` 事件。DSH 进程直接退出时，进行中的工位不会自动收工，需等下次事件或后续扩展。
- 会话 ID 属于元数据；仍建议只在本机查看 inbox 文件。

## 虚构事件自检

```powershell
node --test desktop-pet/integrations/dsh/tests/wang-bun.test.mjs
```

预期输出 `9 pass / 0 fail`。覆盖：

- `turn/start`、全部 `turn/end` 映射、未知状态和 fork 种子不投影；
- 事件 ID 稳定性、非法会话/事件被忽略；
- 只写元数据、不泄漏提示词；
- `inbox` 文件名、原子写入、无残留 `.tmp`；
- 写失败只记录警告，不阻断后续事件；
- `apply()` 只订阅 `session/event` 并只写入可投影记录。

该命令不需要任何真实 DSH 或 WangBun 数据；可重复运行。仓库现有 `node desktop-pet/test_provider_plugins.cjs` 仍覆盖基础映射。

## 真实宿主安装步骤

以下步骤用于后续的真实宿主联调。执行前先退出相关 DSH 会话或选一个不影响工作的 profile；不要在自检阶段改动用户常驻服务。

1. 确认 DSH 版本与插件文件。插件使用 Cordis `{name, inject, apply}` 形状，本机只读确认于 DSH `0.2.1-rc.3`。
2. 找到 DSH home 的 profile 目录：默认 `~/.dsh/profiles/<profile>`（可用 `$DSH_HOME` 覆盖；Windows 通常为 `%USERPROFILE%\.dsh\profiles\<profile>`）。要加装插件的 profile 应包含 `package.json` 与 `cordis.patch.yml`；`cordis.yml` 是 DSH 管理的空根，不要手改。
3. 把 `desktop-pet/integrations/dsh/wang-bun.mjs` 放进该 profile 目录，或使用绝对 `file:///` URL。然后在 `cordis.patch.yml` 增加一行（`id` 在 profile 内唯一）：

   ```yaml
   - id: wang-bun-dsh
     name: './wang-bun.mjs'
     config:
       runtime: 'C:\Users\<用户名>\AppData\Local\WangBun\runtime\bridge'
   ```

   也可以写 `name: 'file:///C:/path/to/xiaolongbao-desktop-office/desktop-pet/integrations/dsh/wang-bun.mjs'`（路径含空格时做 URL 编码）。Loader 以 profile 目录为 `baseUrl`，相对路径从该目录解析。
4. `runtime` 必须指向**当前运行中桌宠**的数据目录，而不是插件文件所在目录：
   - 安装版：`%LOCALAPPDATA%\WangBun\runtime\bridge`
   - 源码模式：`<仓库>\desktop-pet\runtime\bridge`
   - 自定义数据目录：`<--data-dir 或 WANG_BUN_DATA_DIR>\runtime\bridge`

   插件会自动创建 `<runtime>\inbox`。只确认 `connection.json` 与 `inbox` 同级存在，**不要打印或复制 `connection.json`**（其中含本机 bearer token）。
5. 重启该 DSH profile 使补丁层重载。若启用了 DSH HMR，按 HMR 的配置重载流程处理。真实联调时不要在用户常驻服务上直接试。
6. 启动/确认 WangBun 桌宠与桥服务运行，在“设置 → 连接来源”确认 **DeepSeekHarness** 已启用。桥每 0.25 秒处理 inbox，桌宠每 0.5 秒拉取快照。
7. 在 DSH 中发起一个新回合。回合开始/结束各应生成一个 inbox JSON，桌宠随后出现对应工位。

## 验收勾选

- [ ] 自检连续运行两次均为 `9 pass / 0 fail`。
- [ ] DSH 启动输出没有该插件的 import/config 错误；若启用了 loader logs，可见 apply 记录；profile 内 `id: wang-bun-dsh` 未被禁用。
- [ ] `runtime` 与桌宠实际桥目录一致；`inbox/` 与 `connection.json` 同级；未复制或提交 token。
- [ ] 回合开始记录：`source=dsh`、`kind=started`、`run_id=<turn>`、`managed=true`、`observed_at` 为秒级有限数字、`label` 以 `DeepSeekHarness · ` 开头。
- [ ] 回合结束记录：`kind` 与上表一致；同一 `(session.id, seq, type)` 的 `event_id` 稳定，重复投递被桥去重。
- [ ] 记录中不出现提示词、回复正文、工具参数或工具输出。
- [ ] 工位出现：桥已连接、连接来源 `dsh` 已启用、任务未归档；`started` 后约 1 秒内出现打字/开工动画，`completed` 后进入收工/归队流程。工位由共享布局分配，不依赖来源。
- [ ] 真实宿主联调结论只在本清单全部勾选后成立；在此之前保持“尚未完成真实宿主联调”。

## 失败诊断

| 现象 | 首先检查 | 处理 |
| --- | --- | --- |
| 完全没有 `inbox/*.json` | profile 补丁是否生效、`name` 路径是否存在、DSH 是否重启 | 看 DSH 插件 import 错误；改用 `file:///` 绝对路径或把文件复制进 profile；确认 DSH 有 `session/event`（0.2.x）。 |
| inbox 出现 `*.invalid` | 桥拒绝该条 JSON | 桥把无法 `clean_event` 的文件改名为 `.invalid`。检查 `event_id/source/thread_id/kind` 是否非空字符串、`managed` 是否为布尔、`observed_at` 是否为有限秒数；插件自身生成的记录应通过，手写测试文件常缺字段。 |
| 有 JSON 但桌宠无工位 | `runtime` 是否与桌宠桥一致、来源是否启用、桥是否离线 | 用设置页确认 `DeepSeekHarness` 来源；看桌宠底部“本地通知桥未连接”；确认 `connection.json` 与 `inbox` 在同一 runtime 下。 |
| 事件被桥当成重复 | `event_id` 是否重复、DSH 是否重放了同一 `seq` | 这是预期的幂等行为；新回合应有新 `seq/turn`。 |
| 刚出现就消失/不出现 | 任务是否已归档、是否属于旧 run、`observed_at` 是否早于任务状态时间 | 桥会拒绝 `archived`、`old_run`、`stale_observation`；新开回合会重新呈现。 |
| 桌宠显示“等候确认”而非完成 | DSH 本轮 `reason.kind` 是否为 `blocked` | 这是合同映射；若语义不符，先修映射表并补自检，再改文档。 |
| DSH 进程退出后工位仍显示运行 | 插件只观察回合边界，不发送进程心跳/断开事件 | 这是当前合同限制；重启 DSH 后新回合会更新。若需自动收工，需后续扩展 `disconnected`，不在本任务范围。 |

## 只读证据与未知缺口

以下为 2026-11-12 在 Linux 主机上、不加载插件、不读 live 会话的只读检查结果：

- DSH 安装：`~/.local/lib/node_modules/@deepseek-ai/dsh/package.json`（版本 `0.2.1-rc.3`）。
- Profile 组成：`~/.dsh/profiles/<name>/package.json` 的 `dsh.profile.bundles`、`cordis.patch.yml` 用户层、`cordis.yml` 空根；Loader 以 profile 目录锚定 `baseUrl`（`lib/profile-boot-C14i-8IN.js`）。
- 插件加载点：`@deepseek-ai/cordis-plugin-loader` 的 `src/config/tree.ts:112-127`（`import(name)` 解析相对路径/包名）与 `src/config/entry.ts:236`（`{apply}` 插件形状、`name`/`config`/`disabled`，经 `ctx.registry.plugin()` 启动）。
- 事件合同：`@deepseek-ai/dsh-session/lib/types/index.d.ts:61` 的 `session/event(session, event)`；`lib/types/types.d.ts:166,263,274` 的 `TurnEndReasonMap`、`turn/start`、`turn/end`。DSH agent 在回合边界发出这些事件。
- 本机 profile 的 `package.json` 和 `cordis.patch.yml` 可用于确认行结构和 `id` 写法；其中不包含本任务的凭据。

**未知缺口**：没有把插件实际加载进任何运行中的 DSH profile，也没有观察到真实 `session/event`、真实 inbox 文件或 Windows 安装版 runtime。因此“真实宿主加载/联调”仍未验证，必须由后续独立待办完成；本文件不把它标为已完成。