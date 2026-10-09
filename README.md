# BLC OBS Overlay Plugins

用于 BLC 与 OBS 的两个本地直播插件源码集合。

## 项目

- `flag-wish-wall`：Flag 心愿墙，支持主激活词、多个副激活词、审核发布、持久重连与滚屏更新队列。
- `song-quiz-scoreboard`：听歌猜曲自觉积分榜，识别观众的 `+1`、`+2` 弹幕并生成 OBS 积分榜。

两个插件使用独立端口：

- 心愿墙：`18453`
- 猜歌积分榜：`18454`

## 开发与构建

项目后端使用 Python 和 `aiohttp`，桌面发行包使用 PyInstaller 构建。管理页和 OBS 展示页使用 HTML、CSS 与 JavaScript。

构建产物、运行日志、本机 BLC 配置、用户记录及发布压缩包不纳入版本控制。

