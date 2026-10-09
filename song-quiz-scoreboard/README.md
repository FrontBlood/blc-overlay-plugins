# Song Quiz Scoreboard

Version: `0.3.3`

Recognize exact `+1` and `+2` chat messages during a song-quiz session, manage the session through a local admin page, and display a live scoreboard in OBS.

## Installation

For normal users, download a release package and copy the complete `song-quiz-scoreboard` directory into BLC's `data/plugins` directory. Enable the plugin in BLC and fully restart BLC. Do not remove the `_internal` directory beside the executable.

BLC room settings must enable `通过服务器转发消息` (forward messages through the server).

## URLs

- Admin page: `http://127.0.0.1:18454/admin`
- OBS browser source: `http://127.0.0.1:18454/overlay/song-score`

## Scoring rules

- The plugin starts in an idle state and does not score messages.
- Click **Start New Session** in the admin page to clear the previous results and start scoring.
- After trimming leading and trailing whitespace, a message scores only when it is exactly `+1` or `+2`.
- Messages such as `我也+1`, `+10`, and `+2加油` do not score.
- Click **End Session** to stop scoring. OBS keeps the final scoreboard for the session.
- Click **Start New Session** again to clear the previous scores and begin a new session.
- Users with the same score are tied. OBS displays the top 10 by default.

## Fan-medal validation

- The default minimum fan-medal level is `0`, which disables validation.
- When set to a positive value, only messages at or above the threshold are accepted.
- If the event has no level field, it is treated as below the threshold.
- The current version validates only the level value in the event; it does not verify that the fan medal belongs to the current livestream room.

## Admin features

- Start, end, and clear the current session.
- Send local test messages for `+1`, `+2`, and different fan-medal levels.
- Set a score directly, manually add or subtract one point, and delete a user.
- Configure the title, number of displayed users, font size, title color, username color, score color, panel color, and transparency.
- Inspect BLC events, received messages, successful scores, non-command messages, pre-session rejections, and fan-medal rejections.

## Data and connection

- Scores are held in process memory only; they do not persist across sessions or restarts.
- Ending a session stops scoring but does not immediately clear the final scoreboard from OBS.
- After a BLC WebSocket disconnect, the plugin retries every 5 seconds while the HTTP/OBS service continues running.
- The OBS page restores the scoreboard, session, and display settings from snapshots.

For weekly or monthly leaderboards, use a separate long-term data layer; this version does not provide one.

## Troubleshooting

- **No BLC events**: enable `通过服务器转发消息` in the BLC room settings.
- **Messages do not score**: make sure a session is active and the message is exactly `+1` or `+2`.
- **No one scores after enabling a level threshold**: check whether BLC events contain a fan-medal level.
- **`WinError 10048`**: port `18454` is already in use. Stop the duplicate instance or edit `config.json`.

## Run from source and test

From the repository root:

```powershell
python song-quiz-scoreboard\main.py
python song-quiz-scoreboard\tests\test_persistence.py
```

<details>
<summary>中文附录</summary>

# 听歌猜曲自觉积分榜

当前版本：`0.3.3`

在一场听歌猜曲活动中识别观众发送的 `+1`、`+2` 弹幕，通过管理页控制活动并在 OBS 中实时展示排行榜。

## 安装

普通用户应下载发行包，将完整的 `song-quiz-scoreboard` 目录复制到 BLC 的 `data/plugins` 目录，启用插件后完全重启 BLC。请勿删除 exe 旁的 `_internal` 目录。

BLC 房间设置必须开启“通过服务器转发消息”。

## 地址

- 管理页：`http://127.0.0.1:18454/admin`
- OBS 浏览器源：`http://127.0.0.1:18454/overlay/song-score`

## 计分规则

- 插件启动后处于待机状态，不接受计分。
- 管理页点击“开始新活动”后清空上一场结果并开启计分。
- 弹幕去除首尾空格后完整等于 `+1` 时增加 1 分，完整等于 `+2` 时增加 2 分。
- `我也+1`、`+10`、`+2加油` 等普通聊天不会计分。
- 点击“结束本次活动”后停止接收分数，OBS 保留本场最终榜单。
- 再次点击“开始新活动”会清空上一场积分并进入下一场。
- 同分用户并列，OBS 默认显示前 10 名。

## 粉丝牌验证

- 最低粉丝牌等级默认为 `0`，表示关闭验证。
- 设置正数后，只接受等级不低于门槛的弹幕。
- 等级字段缺失时按不满足门槛处理。
- 当前版本只验证事件中的等级值，不验证粉丝牌所属直播间。

## 管理功能

- 开始、结束和清空当前活动。
- 本地测试 `+1`、`+2` 和不同粉丝牌等级。
- 直接设分、手动加减 1 分、删除用户。
- 配置榜单标题、显示人数、字号、标题色、用户名颜色、积分颜色、面板颜色和透明度。
- 查看 BLC 事件、读取弹幕、成功计分、非指令、未开场拒绝和粉丝牌拒绝数量。

## 数据与连接

- 当前积分仅保存在进程内存中，不会跨活动或跨重启累计。
- 结束活动只停止计分，不会立即清除 OBS 中的最终榜单。
- BLC WebSocket 断开后每 5 秒尝试重连，HTTP/OBS 展示服务继续运行。
- OBS 页面通过快照恢复榜单、场次和显示配置。

如果需要周榜或月榜，应使用独立的长期数据层；当前版本没有提供该功能。

## 故障排查

- BLC 事件始终为 0：确认房间设置已开启“通过服务器转发消息”。
- 弹幕不计分：确认活动已经开始，并且弹幕完整等于 `+1` 或 `+2`。
- 等级门槛开启后无人计分：检查 BLC 事件是否包含粉丝牌等级。
- 启动时报 `WinError 10048`：端口 `18454` 已被占用，请关闭重复实例或修改 `config.json`。

## 从源码运行与测试

在仓库根目录安装依赖后执行：

```powershell
python song-quiz-scoreboard\main.py
python song-quiz-scoreboard\tests\test_persistence.py
```

</details>
