# BLC OBS Overlay Plugins

面向 [BLC（Bilibili Live Chat）](https://github.com/xfgryujk/blivechat) 与 OBS 浏览器源的本地直播插件集合。

| 插件 | 功能 | 管理页 | OBS 浏览器源 |
| --- | --- | --- | --- |
| [Flag 心愿墙](flag-wish-wall/) | 从弹幕收集心愿，支持主词、副词、审核和连续滚屏 | `http://127.0.0.1:18453/admin` | `http://127.0.0.1:18453/overlay/wish-wall` |
| [听歌猜曲积分榜](song-quiz-scoreboard/) | 在活动场次中识别 `+1`、`+2` 弹幕并实时计分 | `http://127.0.0.1:18454/admin` | `http://127.0.0.1:18454/overlay/song-score` |

两个插件相互独立，可以同时运行。

> 本项目是社区插件，不属于 BLC、哔哩哔哩或 OBS 官方项目。

## 适用环境

- Windows 10/11
- BLC 1.10.3（其他版本尚未系统验证）
- OBS Studio 浏览器源
- 从源码运行时需要 Python 3.10 或更高版本

## 普通用户安装

1. 优先从 GitHub Releases 下载插件发行包；不要把仓库的 Source code 压缩包直接当作可运行插件。若尚未提供 Release，请按下文从源码构建。
2. 解压后，将 `flag-wish-wall` 和/或 `song-quiz-scoreboard` 整个目录复制到 BLC 的 `data/plugins` 目录。
3. 在 BLC 中启用插件并完全重启 BLC。
4. 在 BLC 房间设置中开启“通过服务器转发消息”。
5. 打开对应管理页完成配置和本地测试。
6. 在 OBS 中新增“浏览器”来源，填入上表中的 OBS 地址。

发行目录中的 exe、`_internal` 和页面文件必须保持原有相对位置。端口冲突时请先修改插件目录中的 `config.json`，再同步修改 OBS 地址。

## 从源码运行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python flag-wish-wall\main.py
```

另开一个终端运行积分榜：

```powershell
.venv\Scripts\Activate.ps1
python song-quiz-scoreboard\main.py
```

直接运行源码时不会自动获得 BLC 注入的 `BLC_PORT` 和 `BLC_TOKEN`；此模式主要用于管理页和本地测试。正式接收直播弹幕时应由 BLC 启动插件。

## 构建 Windows 发行包

```powershell
python -m pip install -r requirements-dev.txt
pyinstaller --noconfirm --clean flag-wish-wall\flag-record-board.spec
pyinstaller --noconfirm --clean song-quiz-scoreboard\self-score-board.spec
```

PyInstaller 只生成程序运行目录。发布时还需要把各插件的 `admin.html`、`overlay.html`、`config.json`、`plugin.json` 和 `README.md` 放到对应程序目录中。

## 数据与隐私

- 两个服务默认只监听 `127.0.0.1`，不会直接向局域网或公网开放管理页。
- BLC 提供的连接令牌只从进程环境变量读取，不写入仓库配置。
- 心愿墙内容保存在插件目录的 `records.json`，该运行数据不会提交到 Git。
- 猜歌积分只保存在当前进程内存中，结束进程后不会保留。
- `plugin.log` 可能包含运行错误信息；公开反馈问题前请自行检查并移除敏感内容。

## 故障排查

- 管理页打不开：确认插件已启动，并检查 `18453` 或 `18454` 是否被其他程序占用。
- OBS 没有画面：先在普通浏览器中打开对应 OBS 地址，再确认 OBS 浏览器源没有缓存旧页面。
- 收不到弹幕：确认 BLC 房间设置已开启“通过服务器转发消息”。
- 管理页能测试但直播弹幕无效：检查粉丝牌等级门槛及 BLC 事件诊断计数。
- 出现 `WinError 10048`：端口已被其他进程占用，关闭重复实例或修改 `config.json` 端口。

更详细的规则见各插件目录中的 README。

## 仓库内容

```text
flag-wish-wall/          心愿墙源码、页面、配置与测试
song-quiz-scoreboard/    猜歌积分榜源码、页面、配置与测试
requirements.txt        运行依赖
requirements-dev.txt    构建与测试依赖
```

构建产物、运行日志、本机 BLC 设置、用户记录和发布压缩包不纳入版本控制。

## 许可证

本项目采用 [MIT License](LICENSE)。你可以使用、修改、分发和用于商业用途，但必须保留原始版权与许可证声明。软件按“原样”提供，不附带任何担保。

