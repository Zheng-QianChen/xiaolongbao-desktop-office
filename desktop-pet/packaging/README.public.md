# 小笼包桌面事务所

让本机 AI 任务变成桌边的小包子：开工时进屋，收工后合上电脑，回来挤在大望包身边。所有软件共用工位，归队的小包子不随小屋翻页消失。

这是 Windows 10/11 x64 本地桌宠，包含透明桌面窗口、浏览器通知面板和消息桥。当前版本是 **0.1.1 预览版**。软件正式名称为「小笼包桌面事务所」，主角仍叫望包 / 小笼望。

## 下载与启动

从本仓库 Releases 下载：

- `Xiaolongbao-Desktop-Office-0.1.1-windows-x64-setup.exe`：当前用户安装，提供开始菜单入口和卸载程序。
- `Xiaolongbao-Desktop-Office-0.1.1-windows-x64-portable.zip`：完整解压后双击 `WangBun.exe`，保留旁边的 `_internal` 文件夹。

两种版本均自带 Python、Tk 和图片资源，无需额外安装运行环境。不自动添加开机启动。预览版没有代码签名；`SHA256SUMS.txt` 提供文件校验值。

右键打开菜单；仅点击“退出桌宠”才退出，同时关闭该实例自己的桥服务。重复启动同一个数据目录不会生成第二个窗口。右键“设置”可选择连接来源、缩放、置顶、文字牌、移动锁定和订阅/助手入口。自由模式支持拖动；黑工模式自动安排工位；Ctrl+滚轮调整大小，普通滚轮翻小屋。

## 任务与消息

- 自动观察 Codex、Cursor 和 ZCode 的本地 GUI 会话状态。Codex/Cursor 的未读跟随原软件；双击小包子跳转会话，不伪造已读。ZCode 当前仅能跳转工作区。
- Claude Code 使用自愿安装的通知 hooks；DeepSeekHarness 提供 `desktop-pet/integrations/dsh/wang-bun.mjs` 插件。TUI 不推测已读，可在面板确认。
- Cursor 精确会话跳转需要附带的扩展源码：运行 `python desktop-pet/integrations/cursor/build_vsix.py`，再在 Cursor 中安装生成的 VSIX。
- 完成未读的小包子保留在大望包身边；原软件确认已读后停留 9 秒再离开。任务再次运行时重新分配共享工位。
- 订阅与助手设置支持 RSS/Atom、IMAP SSL 邮件标题、项目通知，以及用户自行配置的 OpenAI 兼容接口聊天与选中通知摘要。

GUI 集成依赖各软件的本地状态格式；升级后可能需要适配。DeepSeekHarness 插件已做事件适配测试，尚未完成真实宿主联调。软件不会替用户批准 Agent 的操作。

## AI / MCP 接入

运行以下命令生成可复制到 AI 客户端的 MCP 配置：

```powershell
.\WangBun-cli.exe mcp --print-config
```

先启动桌宠，再使用 MCP 的连接管理、项目通知、RSS、邮箱及摘要工具。MCP 使用独立控制台程序，stdout 只传输协议内容。不要把 GUI 程序 `WangBun.exe` 用作 stdio MCP 命令。

本机脚本可以发送项目消息：

```powershell
.\WangBun-cli.exe publish --channel builds --create "构建通知" --id build-001 --title "构建完成"
```

查看 Claude hooks 配置（此命令只预览）：

```powershell
.\WangBun-cli.exe setup-hooks --user --source claude --preview
```

去掉 `--preview` 才会写入用户配置，并备份原文件。DeepSeekHarness 的 `runtime` 设置应指向 `%LOCALAPPDATA%\WangBun\runtime\bridge`。

## 本地数据与网络

安装版和免安装版的数据均保存在 `%LOCALAPPDATA%\WangBun\runtime`，不写入安装目录。卸载保留此目录，便于重新安装；如需清除，退出桌宠后手动删除。源码模式默认仍写在 `desktop-pet/runtime`。可通过 `--data-dir "D:\MyPetData"` 或 `WANG_BUN_DATA_DIR` 指定独立目录。

从 0.1.0 升级会沿用原数据目录、安装标识和命令行入口，已有设置、MCP 配置和通知 hooks 无需因改名而迁移。`WangBun.exe` / `WangBun-cli.exe` 是保留的兼容入口。

没有配置 RSS、邮箱或模型时，不会连接这些外部服务。模型请求仅在用户聊天或选择摘要时发送；密钥和邮箱密码在 Windows 上用当前用户 DPAPI 加密保存在本地。GUI 观察器只投射任务状态元数据；通知内容保存在本机。桥只监听 `127.0.0.1`，默认端口 8768，被占用时使用空闲端口，设置入口自动读取实际地址。

发布包和源码仓库不含维护者的任务记录、聊天记录、密钥、邮箱配置或本机数据库。

## 源码开发与打包

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r desktop-pet/requirements-build.txt
.\.venv\Scripts\python.exe desktop-pet/desktop_app.py
.\.venv\Scripts\python.exe -m unittest discover -s desktop-pet -p "test_*.py"
.\.venv\Scripts\python.exe desktop-pet/packaging/build_windows.py
# 如已安装 Inno Setup，可以同时构建安装程序：
.\.venv\Scripts\python.exe desktop-pet/packaging/build_windows.py --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

构建必须在 Windows x64 上运行。输出位于 `desktop-pet/release`。PyInstaller 使用显式资源清单，构建不会复制 `runtime`、制作历史或私人配置。打包机制参考 [PyInstaller 运行时文档](https://pyinstaller.org/en/stable/runtime-information.html) 和 [Inno Setup 当前用户安装说明](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)。

## 许可与制作说明

原创程序代码以 [MIT](desktop-pet/LICENSE) 开源。角色和图片素材单独说明，见 [ASSETS.md](desktop-pet/ASSETS.md)；依赖许可见 [THIRD_PARTY_NOTICES.md](desktop-pet/THIRD_PARTY_NOTICES.md)。这是非官方同人项目，制作使用了 AI 辅助编程和图像工具。
