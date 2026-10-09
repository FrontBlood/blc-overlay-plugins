# Flag Wish Wall

Version: `0.3.2`

Collect wishes from BLC-forwarded live-chat messages and manage them through a local admin page. The OBS browser source supports horizontal or vertical layouts, multiple scroll directions, and continued service operation during connection interruptions.

## Installation

For normal users, download a release package and copy the complete `flag-wish-wall` directory into BLC's `data/plugins` directory. Enable the plugin in BLC and fully restart BLC. Do not remove the `_internal` directory beside the executable.

BLC room settings must enable `通过服务器转发消息` (forward messages through the server).

## URLs

- Admin page: `http://127.0.0.1:18453/admin`
- OBS browser source: `http://127.0.0.1:18453/overlay/wish-wall`

## Activation rules

### Primary trigger

- Matches only at the beginning of a chat message.
- ASCII letters are case-insensitive: `Flag`, `flag`, and `FLAG` are equivalent.
- When stored, the primary trigger is removed from the beginning and only the following wish text is kept.

Example: with `Flag` as the primary trigger, `flag I hope today's stream goes well` is stored as `I hope today's stream goes well`.

### Secondary triggers

- Add multiple secondary triggers from the admin page, or remove all of them to disable secondary-trigger matching.
- Matches anywhere in a chat message and is case-insensitive for ASCII letters.
- A secondary trigger is used only for matching. Once matched, the complete original message is stored; text before and after the trigger is not removed.
- Choose whether a match is published to the scroll immediately or placed in the moderation queue first.

Example: with `上舰` as a secondary trigger, `今天我想上舰！` is stored in full as `今天我想上舰！`.

### Priority and deduplication

- If a message matches both primary and secondary triggers, the primary-trigger rule takes priority.
- Multiple matching secondary triggers still create only one record.
- A primary trigger appearing in the middle of a message does not count as a primary match, but the message can still match a secondary trigger.

## Default limits

- The default minimum fan-medal level is `3`; set it to `0` to disable level validation.
- If the BLC event does not include a fan-medal level while the threshold is greater than `0`, the message is rejected.
- Wish length is unlimited by default; configure a limit from 1 to 500 characters in the admin page.
- Blocked words are separated with the full-width Chinese semicolon `；`.
- A user may submit multiple wishes.

## OBS display

- The default format is `username wish text`, with one fixed space between the username and body.
- Entries are separated by `★` by default; change the separator in the admin page.
- Supports vertical or horizontal text and upward/downward or left/right scrolling.
- Consecutive Latin letters remain together in vertical mode instead of being split into one letter per line.
- Configure font color, size, outline, scroll speed, and title.
- Published records are ordered newest first.

Display updates use a queue. New submissions, deletions, moderation decisions, or display-setting changes that occur during the current scroll cycle are merged after the current content has fully left the screen instead of restarting the animation immediately. Runtime counters and periodic calibration do not interrupt the scroll.

## Data and connection

- Wishes are persisted in `records.json` inside the plugin directory.
- After a BLC WebSocket disconnect, the plugin retries every 5 seconds while the HTTP/OBS service continues running.
- The OBS page reconciles published records every 30 seconds and resynchronizes after network or page recovery.
- The admin page, overlay page, and API disable caching to reduce stale pages in long-running OBS sessions.

## Admin page

The admin page can:

- Add or remove multiple secondary triggers.
- Publish secondary-trigger matches immediately or send them to moderation.
- Add moderated wishes to the scroll.
- Delete stored records.
- Change the title, separator, layout, direction, speed, colors, font size, and outline.
- Set the fan-medal threshold, wish-length limit, and blocked words.
- Send local test messages and inspect receive diagnostics.

## Troubleshooting

- **No BLC events**: enable `通过服务器转发消息` in the BLC room settings.
- **Events arrive but nothing is stored**: check triggers, fan-medal validation, and blocked-word counters.
- **OBS does not show new content**: check whether the content is still waiting for moderation, then open the OBS URL directly in a normal browser.
- **`WinError 10048`**: port `18453` is already in use. Stop the duplicate instance or edit `config.json`.

## Run from source and test

From the repository root:

```powershell
python flag-wish-wall\main.py
python flag-wish-wall\tests\test_activation_rules.py
python flag-wish-wall\tests\test_persistence.py
```

<details>
<summary>中文附录</summary>

# Flag 心愿墙

当前版本：`0.3.2`

从 BLC 转发的直播弹幕中收集心愿，并通过本地管理页审核、配置和删除内容。OBS 页面支持横排或竖排、上下或左右滚动，并在连接波动时保持展示服务运行。

## 安装

普通用户应下载发行包，将完整的 `flag-wish-wall` 目录复制到 BLC 的 `data/plugins` 目录，启用插件后完全重启 BLC。请勿删除 exe 旁的 `_internal` 目录。

BLC 房间设置必须开启“通过服务器转发消息”。

## 地址

- 管理页：`http://127.0.0.1:18453/admin`
- OBS 浏览器源：`http://127.0.0.1:18453/overlay/wish-wall`

## 激活规则

### 主激活词

- 只在弹幕句首匹配。
- 英文字母不区分大小写，例如 `Flag`、`flag`、`FLAG` 等价。
- 入库时删除句首主词，只保留主词后的心愿内容。

示例：主词为 `Flag` 时，`flag 希望今天直播顺利` 入库为 `希望今天直播顺利`。

### 副激活词

- 可在管理页添加多个副词，也可以全部删除以关闭副词检测。
- 在弹幕任意位置匹配，英文字母不区分大小写。
- 副词只用于判断是否命中；命中后整条原始弹幕入库，不截断副词前后的内容。
- 可选择自动加入滚屏，或先入库等待管理页审核。

示例：副词为 `上舰` 时，`今天我想上舰！` 会完整入库为 `今天我想上舰！`。

### 优先级与去重

- 同一弹幕同时命中主词和副词时，以主词为准。
- 同一弹幕命中多个副词时也只产生一条记录。
- 主词出现在句中不会视为主词，但弹幕仍可继续匹配副词。

## 默认限制

- 默认最低粉丝牌等级为 `3`；设为 `0` 可关闭等级验证。
- BLC 事件缺少粉丝牌等级且门槛大于 `0` 时，弹幕会被拒绝。
- 默认不限制单条心愿长度，可在管理页设置为 1～500 字。
- 屏蔽词使用中文全角分号 `；` 分隔。
- 同一用户可以提交多条心愿。

## OBS 展示

- 默认格式为 `用户名 心愿内容`，用户名和正文之间固定保留一个空格。
- 条目默认使用 `★` 分隔，可在管理页修改。
- 支持竖向或横向文字，以及上下或左右滚动。
- 英文连续字母在竖排模式中保持为整体，不拆成逐字母竖排。
- 支持字体颜色、字号、描边、滚动速度和标题配置。
- 已发布记录按最新内容在前排列。

展示更新采用队列：当前一轮滚动期间发生的新增、删除、审核发布或显示配置变化不会立即重启动画，而是在本轮内容完整滚出画面后合并应用。运行计数变化和定期校准不会打断滚动。

## 数据与连接

- 心愿持久保存在插件目录的 `records.json`。
- BLC WebSocket 断开后每 5 秒尝试重连，HTTP/OBS 展示服务继续运行。
- OBS 页面每 30 秒校准已发布记录，并在网络或页面恢复时重新同步。
- 管理页、展示页和 API 禁止缓存，减少 OBS 长期使用旧页面的情况。

## 管理页

管理页可以：

- 添加、删除多个副激活词。
- 选择副词自动发布或进入待审核。
- 将待审核内容加入滚屏。
- 删除已记录内容。
- 修改标题、分隔符、排布、方向、速度、颜色、字号和描边。
- 设置粉丝牌等级、字数上限和屏蔽词。
- 发送本地测试弹幕并查看接收诊断。

## 故障排查

- BLC 事件始终为 0：确认房间设置已开启“通过服务器转发消息”。
- 有事件但没有入库：检查激活词、粉丝牌等级和屏蔽词统计。
- OBS 看不到新内容：确认内容是否仍处于待审核状态，并用浏览器直接打开 OBS 地址。
- 启动时报 `WinError 10048`：端口 `18453` 已被占用，请关闭重复实例或修改 `config.json`。

## 从源码运行与测试

在仓库根目录安装依赖后执行：

```powershell
python flag-wish-wall\main.py
python flag-wish-wall\tests\test_activation_rules.py
python flag-wish-wall\tests\test_persistence.py
```

</details>
