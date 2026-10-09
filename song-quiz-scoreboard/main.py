import asyncio
import contextlib
import json
import logging
import os
import re
import sys
import time
import webbrowser
from pathlib import Path

from aiohttp import ClientSession, WSMsgType, web


BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = BASE / "config.json"
ADMIN_PAGE = BASE / "admin.html"
OVERLAY_PAGE = BASE / "overlay.html"

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 18454,
    "top_n": 10,
    "min_medal_level": 0,
    "board_title": "猜歌积分榜",
    "font_size": 30,
    "title_color": "#ffe98a",
    "name_color": "#fff8ea",
    "score_color": "#ffb7d5",
    "panel_color": "#241b33",
    "panel_opacity": 0.86,
}
BLC_RETRY_SECONDS = 5


def save_json_atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    temporary.replace(path)


def clamp_int(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def clamp_float(value, default, low, high):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def normalize_color(value, default):
    color = str(value or default).strip().lower()
    return color if re.fullmatch(r"#[0-9a-f]{6}", color) else default


def load_config():
    try:
        raw = json.loads(CONFIG_PATH.read_text("utf-8-sig"))
    except Exception:
        raw = {}
    config = {**DEFAULT_CONFIG, **(raw if isinstance(raw, dict) else {})}
    config["host"] = str(config.get("host") or "127.0.0.1")
    config["port"] = clamp_int(config.get("port"), 18454, 1024, 65535)
    config["top_n"] = clamp_int(config.get("top_n"), 10, 1, 100)
    config["min_medal_level"] = clamp_int(config.get("min_medal_level"), 0, 0, 1000)
    config["board_title"] = str(config.get("board_title") or "猜歌积分榜").strip()[:30] or "猜歌积分榜"
    config["font_size"] = clamp_int(config.get("font_size"), 30, 16, 72)
    config["panel_opacity"] = clamp_float(config.get("panel_opacity"), 0.86, 0.0, 1.0)
    for key in ("title_color", "name_color", "score_color", "panel_color"):
        config[key] = normalize_color(config.get(key), DEFAULT_CONFIG[key])
    config = {key: config[key] for key in DEFAULT_CONFIG}
    save_json_atomic(CONFIG_PATH, config)
    return config


def direct_value(data, keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return value
    return None


def as_level(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", str(value))
        return int(match.group(1)) if match else None


MEDAL_LEVEL_KEYS = (
    "medalLevel", "medal_level", "fansMedalLevel", "fans_medal_level",
    "fanMedalLevel", "fan_medal_level", "fansLevel", "fans_level",
)


def find_medal_level(node):
    if not isinstance(node, dict):
        return None
    level = as_level(direct_value(node, MEDAL_LEVEL_KEYS))
    if level is not None:
        return level
    for key, value in node.items():
        normalized = str(key).lower().replace("_", "")
        if "medal" not in normalized and "fan" not in normalized and "粉丝牌" not in str(key):
            continue
        if isinstance(value, dict):
            level = as_level(direct_value(value, MEDAL_LEVEL_KEYS + ("level", "lv", "rank")))
        elif isinstance(value, (list, tuple)) and value:
            level = as_level(value[0])
        else:
            level = as_level(value)
        if level is not None:
            return level
    return None


def is_danmaku_marker(marker):
    if marker is None:
        return True
    text = str(marker).strip().lower()
    if not text:
        return True
    if text.replace(".", "", 1).isdigit():
        try:
            return int(float(text)) not in (0, 5, 51, 52, 53)
        except ValueError:
            return True
    if "blc_init" in text:
        return False
    rejected = ("gift", "guard", "super_chat", "superchat", "heartbeat", "popularity", "like", "enter", "interact")
    return not any(word in text for word in rejected)


def extract_danmakus(payload):
    found = []
    positions = {}

    def add(uid, name, content, medal_level=None):
        item = (str(uid), str(name or uid), str(content or ""), as_level(medal_level))
        identity = item[:3]
        if not item[2]:
            return
        if identity not in positions:
            positions[identity] = len(found)
            found.append(item)
            return
        index = positions[identity]
        previous = found[index]
        if item[3] is not None and (previous[3] is None or item[3] > previous[3]):
            found[index] = item

    def walk(node, inherited_marker=None, inherited_medal=None):
        if isinstance(node, list):
            for child in node:
                walk(child, inherited_marker, inherited_medal)
            return
        if not isinstance(node, dict):
            return
        own_marker = direct_value(node, ("cmd", "type", "event", "message_type", "msg_type"))
        marker = own_marker if own_marker is not None else inherited_marker
        own_medal = find_medal_level(node)
        medal_level = own_medal if own_medal is not None else inherited_medal
        marker_text = str(marker).strip().lower() if marker is not None else ""
        command_data = node.get("data")
        if marker_text == "50" and isinstance(command_data, list) and len(command_data) > 4:
            uid = command_data[16] if len(command_data) > 16 and command_data[16] not in (None, "") else command_data[2]
            add(uid, command_data[2] or uid, command_data[4], command_data[10] if len(command_data) > 10 else None)
        text = direct_value(node, ("content", "msg", "text", "message"))
        uid = direct_value(node, ("uid", "user_id", "userid", "user_uid", "open_id", "mid"))
        name = direct_value(node, ("authorName", "author_name", "uname", "username", "user_name", "nickname", "name"))
        user = node.get("user")
        if isinstance(user, dict):
            uid = uid if uid is not None else direct_value(user, ("uid", "id", "user_id", "user_uid", "open_id", "mid"))
            name = name if name is not None else direct_value(user, ("authorName", "author_name", "uname", "name", "username", "user_name", "nickname"))
            user_medal = find_medal_level(user)
            medal_level = user_medal if user_medal is not None else medal_level
        if is_danmaku_marker(marker) and text is not None and uid is not None:
            add(uid, name or uid, text, medal_level)
        for child in node.values():
            if isinstance(child, (dict, list)):
                walk(child, marker, medal_level)

    walk(payload)
    return found


def parse_points(message):
    command = str(message).strip()
    if command == "+1":
        return 1
    if command == "+2":
        return 2
    return None


class ScoreStore:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.players = {}
        self.active = False
        self.session_number = 0
        self.started_at = None
        self.ended_at = None

    def session_state(self):
        return {
            "active": self.active,
            "session_number": self.session_number,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    def snapshot(self):
        ordered = sorted(self.players.values(), key=lambda item: (-item["score"], item["updated_at"], item["uid"]))
        result = []
        previous_score = None
        current_rank = 0
        for index, item in enumerate(ordered, 1):
            if item["score"] != previous_score:
                current_rank = index
                previous_score = item["score"]
            result.append({**item, "rank": current_rank})
        return result

    async def increment(self, uid, name, points, medal_level=None):
        async with self.lock:
            if not self.active:
                return None
            now = time.time()
            player = self.players.get(uid, {"uid": uid, "name": name or uid, "score": 0, "medal_level": 0, "updated_at": now})
            player["name"] = name or player["name"]
            player["score"] = max(0, int(player["score"]) + int(points))
            if medal_level is not None:
                player["medal_level"] = max(0, int(medal_level))
            player["updated_at"] = now
            self.players[uid] = player
            return dict(player)

    async def set_score(self, uid, name, score):
        async with self.lock:
            now = time.time()
            player = self.players.get(uid, {"uid": uid, "name": name or uid, "score": 0, "medal_level": 0, "updated_at": now})
            player["name"] = str(name or player["name"] or uid)
            player["score"] = max(0, int(score))
            player["updated_at"] = now
            self.players[uid] = player
            return dict(player)

    async def delete(self, uid):
        async with self.lock:
            if uid not in self.players:
                return False
            del self.players[uid]
            return True

    async def clear(self):
        async with self.lock:
            self.players.clear()

    async def start(self):
        async with self.lock:
            self.players.clear()
            self.active = True
            self.session_number += 1
            self.started_at = time.time()
            self.ended_at = None
            return self.session_state()

    async def end(self):
        async with self.lock:
            self.active = False
            self.ended_at = time.time()
            return self.session_state()

    async def reset_current(self):
        async with self.lock:
            self.players.clear()
            return self.session_state()


class ScoreApp:
    def __init__(self, store, config):
        self.store = store
        self.config = config
        self.clients = set()
        self.blc_connected = False
        self.last_error = ""
        self.blc_events = 0
        self.last_event = ""
        self.received = 0
        self.matched = 0
        self.ignored = 0
        self.rejected_inactive = 0
        self.rejected_medal = 0

    async def broadcast(self, payload):
        message = json.dumps(payload, ensure_ascii=False)
        stale = []
        for client in tuple(self.clients):
            try:
                await client.send_str(message)
            except Exception:
                stale.append(client)
        for client in stale:
            self.clients.discard(client)

    def public_settings(self):
        return {key: self.config[key] for key in (
            "top_n", "min_medal_level", "board_title", "font_size",
            "title_color", "name_color", "score_color", "panel_color", "panel_opacity",
        )}

    async def accept_danmaku(self, uid, name, message, medal_level=None):
        self.received += 1
        points = parse_points(message)
        if points is None:
            self.ignored += 1
            return None, "command_mismatch"
        if not self.store.active:
            self.rejected_inactive += 1
            return None, "session_inactive"
        level = as_level(medal_level)
        minimum = self.config["min_medal_level"]
        if minimum > 0 and (level is None or level < minimum):
            self.rejected_medal += 1
            return None, "medal_too_low"
        player = await self.store.increment(str(uid), str(name or uid), points, level)
        self.matched += 1
        await self.broadcast({"type": "scoreboard", "players": self.store.snapshot(), "session": self.store.session_state(), "changed_uid": player["uid"]})
        return player, "recorded"

    def status(self):
        return {
            "blc_connected": self.blc_connected,
            "overlay_clients": len(self.clients),
            "blc_events": self.blc_events,
            "last_event": self.last_event,
            "received": self.received,
            "matched": self.matched,
            "ignored": self.ignored,
            "rejected_inactive": self.rejected_inactive,
            "rejected_medal": self.rejected_medal,
            "player_count": len(self.store.players),
            "last_error": self.last_error,
            "session": self.store.session_state(),
            **self.public_settings(),
        }


async def send_blc_heartbeats(socket):
    while not socket.closed:
        await asyncio.sleep(10)
        await socket.send_json({"cmd": 0, "data": {}})


async def blc_connection(app, admin_url, port, token):
    """Maintain one BLC websocket session until the peer disconnects."""
    url = f"ws://127.0.0.1:{port}/api/plugin/websocket"
    heartbeat_task = None
    try:
        async with ClientSession() as session:
            async with session.ws_connect(
                url,
                headers={"Authorization": f"Bearer {token}"},
                heartbeat=20,
                receive_timeout=45,
            ) as socket:
                app.blc_connected = True
                app.last_error = ""
                logging.info("BLC WebSocket 已连接：%s", url)
                heartbeat_task = asyncio.create_task(send_blc_heartbeats(socket))
                async for message in socket:
                    if message.type != WSMsgType.TEXT:
                        continue
                    try:
                        payload = json.loads(message.data)
                        marker = direct_value(payload, ("cmd", "type", "event", "message_type", "msg_type"))
                        marker_text = str(marker).strip().lower() if marker is not None else "(none)"
                        if marker_text == "5":
                            await asyncio.to_thread(webbrowser.open, admin_url)
                            continue
                        if marker_text != "0" and "blc_init" not in marker_text:
                            app.blc_events += 1
                            app.last_event = marker_text
                        for item in extract_danmakus(payload):
                            await app.accept_danmaku(*item)
                    except Exception as exc:
                        app.last_error = str(exc)
                        logging.exception("BLC 消息处理失败")
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
        app.blc_connected = False


async def blc_loop(app, admin_url):
    """Reconnect forever without taking the HTTP/OBS service down."""
    port = os.getenv("BLC_PORT")
    token = os.getenv("BLC_TOKEN")
    if not port or not token:
        return
    while True:
        try:
            await blc_connection(app, admin_url, port, token)
            app.last_error = "BLC WebSocket 已断开"
            logging.warning("%s", app.last_error)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app.blc_connected = False
            app.last_error = f"BLC 连接失败：{exc}"
            logging.warning("%s；%s 秒后重试", app.last_error, BLC_RETRY_SECONDS)
        await asyncio.sleep(BLC_RETRY_SECONDS)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(BASE / "plugin.log", encoding="utf-8")],
    )
    config = load_config()
    store = ScoreStore()
    app = ScoreApp(store, config)
    @web.middleware
    async def no_cache(request, handler):
        response = await handler(request)
        if request.path in ("/admin", "/overlay/song-score") or request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    server = web.Application(middlewares=[no_cache])

    async def index(_):
        raise web.HTTPFound("/admin")

    async def admin(_):
        return web.Response(text=ADMIN_PAGE.read_text("utf-8"), content_type="text/html")

    async def overlay(_):
        return web.Response(text=OVERLAY_PAGE.read_text("utf-8"), content_type="text/html")

    async def status(_):
        return web.json_response(app.status())

    async def scores(_):
        return web.json_response({"players": store.snapshot(), "session": store.session_state(), "settings": app.public_settings()})

    async def update_config(request):
        data = await request.json()
        title = str(data.get("board_title") or "").strip()[:30]
        if not title:
            raise web.HTTPBadRequest(text="榜单标题不能为空")
        config["board_title"] = title
        config["top_n"] = clamp_int(data.get("top_n"), config["top_n"], 1, 100)
        config["min_medal_level"] = clamp_int(data.get("min_medal_level"), config["min_medal_level"], 0, 1000)
        config["font_size"] = clamp_int(data.get("font_size"), config["font_size"], 16, 72)
        config["panel_opacity"] = clamp_float(data.get("panel_opacity"), config["panel_opacity"], 0.0, 1.0)
        for key in ("title_color", "name_color", "score_color", "panel_color"):
            color = str(data.get(key) or "").strip().lower()
            if not re.fullmatch(r"#[0-9a-f]{6}", color):
                raise web.HTTPBadRequest(text=f"{key} 格式不正确")
            config[key] = color
        save_json_atomic(CONFIG_PATH, config)
        settings = app.public_settings()
        await app.broadcast({"type": "settings", "settings": settings})
        return web.json_response({"ok": True, "settings": settings})

    async def test_score(request):
        data = await request.json()
        player, reason = await app.accept_danmaku(
            str(data.get("uid") or "test-user"),
            str(data.get("name") or "测试观众"),
            str(data.get("text") if data.get("text") is not None else "+1"),
            data.get("medal_level"),
        )
        return web.json_response({"ok": player is not None, "reason": reason, "player": player})

    async def set_player_score(request):
        data = await request.json()
        uid = request.match_info["uid"]
        try:
            score = max(0, min(999999999, int(data.get("score"))))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="score 格式不正确")
        player = await store.set_score(uid, str(data.get("name") or ""), score)
        await app.broadcast({"type": "scoreboard", "players": store.snapshot(), "session": store.session_state(), "changed_uid": uid})
        return web.json_response({"ok": True, "player": player})

    async def delete_player(request):
        uid = request.match_info["uid"]
        if not await store.delete(uid):
            raise web.HTTPNotFound()
        await app.broadcast({"type": "scoreboard", "players": store.snapshot(), "session": store.session_state(), "changed_uid": None})
        return web.json_response({"ok": True})

    async def clear_scores(_):
        await store.clear()
        await app.broadcast({"type": "scoreboard", "players": [], "session": store.session_state(), "changed_uid": None})
        return web.json_response({"ok": True})

    async def start_session(_):
        session = await store.start()
        app.received = 0
        app.matched = 0
        app.ignored = 0
        app.rejected_inactive = 0
        app.rejected_medal = 0
        await app.broadcast({"type": "scoreboard", "players": [], "session": session, "changed_uid": None})
        return web.json_response({"ok": True, "session": session})

    async def end_session(_):
        session = await store.end()
        await app.broadcast({"type": "scoreboard", "players": store.snapshot(), "session": session, "changed_uid": None})
        return web.json_response({"ok": True, "session": session})

    async def reset_session(_):
        session = await store.reset_current()
        await app.broadcast({"type": "scoreboard", "players": [], "session": session, "changed_uid": None})
        return web.json_response({"ok": True, "session": session})

    async def socket_handler(request):
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        app.clients.add(socket)
        await socket.send_str(json.dumps({
            "type": "snapshot", "players": store.snapshot(), "session": store.session_state(), "settings": app.public_settings(),
        }, ensure_ascii=False))
        try:
            async for _ in socket:
                pass
        finally:
            app.clients.discard(socket)
        return socket

    server.router.add_get("/", index)
    server.router.add_get("/admin", admin)
    server.router.add_get("/overlay/song-score", overlay)
    server.router.add_get("/api/status", status)
    server.router.add_get("/api/scores", scores)
    server.router.add_post("/api/config", update_config)
    server.router.add_post("/api/test", test_score)
    server.router.add_post("/api/scores/{uid}", set_player_score)
    server.router.add_delete("/api/scores/{uid}", delete_player)
    server.router.add_delete("/api/scores", clear_scores)
    server.router.add_post("/api/session/start", start_session)
    server.router.add_post("/api/session/end", end_session)
    server.router.add_post("/api/session/reset", reset_session)
    server.router.add_get("/ws/scores", socket_handler)

    runner = web.AppRunner(server)
    await runner.setup()
    blc_task = None
    try:
        await web.TCPSite(runner, config["host"], config["port"]).start()
        logging.info("管理页：http://%s:%s/admin", config["host"], config["port"])
        if os.getenv("BLC_PORT") and os.getenv("BLC_TOKEN"):
            blc_task = asyncio.create_task(
                blc_loop(app, f"http://{config['host']}:{config['port']}/admin"),
                name="blc-reconnect-loop",
            )
        else:
            logging.warning("独立测试模式")
        await asyncio.Event().wait()
    finally:
        if blc_task:
            blc_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await blc_task
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
