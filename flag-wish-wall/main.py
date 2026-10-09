import asyncio
import contextlib
import json
import logging
import os
import re
import sys
import time
import uuid
import webbrowser
from pathlib import Path

from aiohttp import ClientSession, WSMsgType, web

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = BASE / "config.json"
RECORDS_PATH = BASE / "records.json"
ADMIN_PAGE = BASE / "admin.html"
OVERLAY_PAGE = BASE / "overlay.html"
DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 18453,
    "flag": "Flag",
    "secondary_flags": [],
    "secondary_auto_publish": False,
    "blocked_words": "",
    "max_chars": 0,
    "max_records": 200,
    "min_medal_level": 3,
    "wall_title": "心愿墙",
    "entry_separator": "★",
    "layout_mode": "vertical",
    "scroll_axis": "vertical",
    "scroll_speed": 38,
    "font_color": "#fff8e8",
    "font_size": 36,
    "stroke_enabled": True,
    "stroke_color": "#261b2c",
    "stroke_width": 1.0,
}
BLC_RETRY_SECONDS = 5


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def load_config():
    try:
        raw = json.loads(CONFIG_PATH.read_text("utf-8-sig"))
    except Exception:
        raw = {}
    config = {**DEFAULT_CONFIG, **raw}
    config["host"] = str(config.get("host") or "127.0.0.1")
    for key, default, low, high in (
        ("port", 18453, 1024, 65535),
        ("max_chars", 0, 0, 500),
        ("max_records", 200, 20, 2000),
        ("min_medal_level", 3, 0, 1000),
        ("scroll_speed", 38, 10, 200),
        ("font_size", 36, 12, 96),
    ):
        try:
            config[key] = max(low, min(high, int(config.get(key, default))))
        except (TypeError, ValueError):
            config[key] = default
    config["flag"] = str(config.get("flag") or "Flag")[:32]
    secondary_source = raw.get("secondary_flags")
    if not isinstance(secondary_source, list):
        secondary_source = [raw.get("secondary_flag", "")]
    secondary_flags = []
    seen_secondary = set()
    for value in secondary_source[:50]:
        word = str(value or "").replace("\r", "").replace("\n", "").strip()[:32]
        folded = word.casefold()
        if word and folded not in seen_secondary:
            secondary_flags.append(word)
            seen_secondary.add(folded)
    config["secondary_flags"] = secondary_flags
    config.pop("secondary_flag", None)
    config["secondary_auto_publish"] = bool(config.get("secondary_auto_publish", False))
    config["blocked_words"] = str(config.get("blocked_words") or "").replace("\r", "").replace("\n", "")[:500]
    config["wall_title"] = str(config.get("wall_title") or "心愿墙").strip()[:20] or "心愿墙"
    separator = str(config.get("entry_separator", "★")).replace("\r", "").replace("\n", "")
    config["entry_separator"] = separator[:12]
    config["layout_mode"] = "horizontal" if config.get("layout_mode") == "horizontal" else "vertical"
    config["scroll_axis"] = "horizontal" if config.get("scroll_axis") == "horizontal" else "vertical"
    for key, default in (("font_color", "#fff8e8"), ("stroke_color", "#261b2c")):
        config[key] = str(config.get(key) or default).strip().lower()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", config[key]):
            config[key] = default
    config["stroke_enabled"] = bool(config.get("stroke_enabled", True))
    try:
        config["stroke_width"] = max(0.0, min(6.0, float(config.get("stroke_width", 1.0))))
    except (TypeError, ValueError):
        config["stroke_width"] = 1.0
    save_json(CONFIG_PATH, config)
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
    if any(word in text for word in rejected):
        return False
    return True

def extract_danmakus(payload):
    found = []
    seen = set()

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
        is_danmaku = is_danmaku_marker(marker)
        command_data = node.get("data")
        if marker_text == "50" and isinstance(command_data, list) and len(command_data) > 4:
            # BLC SDK Command.ADD_TEXT: data is a positional array, not an object.
            # Fields [2]/[4]/[10]/[16] are author/content/medal/uid. The trailing
            # fields differ between BLC releases, so optional fields use fallbacks.
            uid_value = command_data[16] if len(command_data) > 16 and command_data[16] not in (None, "") else command_data[2]
            item = (
                str(uid_value),
                str(command_data[2] or uid_value),
                str(command_data[4] or ""),
                as_level(command_data[10]) if len(command_data) > 10 else None,
            )
            identity = (item[0], item[1], item[2], item[3])
            if item[2] and identity not in seen:
                seen.add(identity)
                found.append(item)
        text = direct_value(node, ("content", "msg", "text", "message"))
        uid = direct_value(node, ("uid", "user_id", "userid", "user_uid", "open_id", "mid"))
        name = direct_value(node, ("authorName", "author_name", "uname", "username", "user_name", "nickname", "name"))
        user = node.get("user")
        if isinstance(user, dict):
            uid = uid if uid is not None else direct_value(user, ("uid", "id", "user_id", "user_uid", "open_id", "mid"))
            name = name if name is not None else direct_value(user, ("authorName", "author_name", "uname", "name", "username", "user_name", "nickname"))
            user_medal = find_medal_level(user)
            medal_level = user_medal if user_medal is not None else medal_level
        if is_danmaku and text is not None and uid is not None:
            item = (str(uid), str(name or uid), str(text), medal_level)
            identity = (item[0], item[1], item[2], item[3])
            if identity not in seen:
                seen.add(identity)
                found.append(item)
        for child in node.values():
            if isinstance(child, (dict, list)):
                walk(child, marker, medal_level)

    walk(payload)
    return found


def find_flag_match(message, flag, at_start=False):
    if not flag:
        return None
    pattern = re.compile(re.escape(flag), re.IGNORECASE)
    return pattern.match(message) if at_start else pattern.search(message)


def parse_flag_content(message, flag, max_chars, at_start=False):
    match = find_flag_match(message, flag, at_start=at_start)
    if not match:
        return None
    value = message[match.end():].lstrip()
    if not value:
        return None
    if max_chars > 0:
        value = "".join(list(value)[:max_chars])
    value = value.strip()
    return value or None


def contains_flag(message, flag, at_start=False):
    return find_flag_match(message, flag, at_start=at_start) is not None


def first_secondary_match(message, flags):
    """Return the secondary word occurring earliest; configuration order breaks ties."""
    matches = []
    for index, flag in enumerate(flags):
        match = find_flag_match(message, flag)
        if match:
            matches.append((match.start(), index, flag))
    return min(matches)[2] if matches else None


class RecordStore:
    def __init__(self, max_records):
        self.max_records = max_records
        self.lock = asyncio.Lock()
        self.records = self._load()

    def _load(self):
        try:
            raw = json.loads(RECORDS_PATH.read_text("utf-8-sig"))
            if not isinstance(raw, list):
                return []
            result = []
            for item in raw[-self.max_records:]:
                if not isinstance(item, dict):
                    continue
                result.append({
                    "id": str(item.get("id") or uuid.uuid4().hex),
                    "uid": str(item.get("uid") or ""),
                    "name": str(item.get("name") or "观众"),
                    "content": str(item.get("content") or ""),
                    "medal_level": as_level(item.get("medal_level")) or 0,
                    "created_at": float(item.get("created_at") or time.time()),
                    "activation": "secondary" if item.get("activation") == "secondary" else "primary",
                    "published": item.get("published") is not False,
                })
            return result
        except Exception:
            return []

    def _save(self):
        save_json(RECORDS_PATH, self.records)

    async def add(self, uid, name, content, medal_level, activation="primary", published=True):
        async with self.lock:
            record = {
                "id": uuid.uuid4().hex,
                "uid": uid,
                "name": name,
                "content": content,
                "medal_level": medal_level,
                "created_at": time.time(),
                "activation": activation,
                "published": bool(published),
            }
            self.records.append(record)
            self.records = self.records[-self.max_records:]
            self._save()
            return record

    async def delete(self, record_id):
        async with self.lock:
            before = len(self.records)
            self.records = [item for item in self.records if item["id"] != record_id]
            if len(self.records) == before:
                return False
            self._save()
            return True

    async def publish(self, record_id):
        async with self.lock:
            for record in self.records:
                if record["id"] != record_id:
                    continue
                if record["published"]:
                    return dict(record)
                record["published"] = True
                self._save()
                return dict(record)
            return None

    def snapshot(self, published_only=False):
        records = self.records
        if published_only:
            records = [item for item in records if item.get("published") is not False]
        return [dict(item) for item in records]


class FlagRecordApp:
    def __init__(self, store, config):
        self.store = store
        self.config = config
        self.clients = set()
        self.blc_connected = False
        self.last_error = ""
        self.received = 0
        self.recorded = 0
        self.rejected_medal = 0
        self.rejected_blocked = 0
        self.missing_flag = 0
        self.secondary_recorded = 0
        self.blc_events = 0
        self.last_event = ""

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

    async def accept_danmaku(self, uid, name, message, medal_level):
        self.received += 1
        if contains_flag(message, self.config["flag"], at_start=True):
            content = parse_flag_content(message, self.config["flag"], self.config["max_chars"], at_start=True)
            activation = "primary"
        elif first_secondary_match(message, self.config["secondary_flags"]):
            content = str(message).strip()
            if self.config["max_chars"] > 0:
                content = "".join(list(content)[:self.config["max_chars"]]).strip()
            content = content or None
            activation = "secondary"
        else:
            content = None
            activation = "primary"
        if content is None:
            self.missing_flag += 1
            return None, "missing_flag"
        blocked_terms = [term.strip().casefold() for term in self.config["blocked_words"].split("；") if term.strip()]
        if any(term in content.casefold() for term in blocked_terms):
            self.rejected_blocked += 1
            return None, "blocked_word"
        level = as_level(medal_level)
        minimum = self.config["min_medal_level"]
        if minimum > 0 and (level is None or level < minimum):
            self.rejected_medal += 1
            return None, "medal_too_low"
        published = activation == "primary" or self.config["secondary_auto_publish"]
        record = await self.store.add(uid, name, content, level or 0, activation, published)
        self.recorded += 1
        if activation == "secondary":
            self.secondary_recorded += 1
        await self.broadcast({"type": "record_added", "record": record})
        return record, "recorded" if published else "pending_review"

    def public_settings(self):
        return {
            "flag": self.config["flag"],
            "secondary_flags": self.config["secondary_flags"],
            "secondary_auto_publish": self.config["secondary_auto_publish"],
            "blocked_words": self.config["blocked_words"],
            "max_chars": self.config["max_chars"],
            "min_medal_level": self.config["min_medal_level"],
            "wall_title": self.config["wall_title"],
            "entry_separator": self.config["entry_separator"],
            "layout_mode": self.config["layout_mode"],
            "scroll_axis": self.config["scroll_axis"],
            "scroll_speed": self.config["scroll_speed"],
            "font_color": self.config["font_color"],
            "font_size": self.config["font_size"],
            "stroke_enabled": self.config["stroke_enabled"],
            "stroke_color": self.config["stroke_color"],
            "stroke_width": self.config["stroke_width"],
        }

    def status(self):
        return {
            "blc_connected": self.blc_connected,
            "overlay_clients": len(self.clients),
            "received": self.received,
            "recorded": self.recorded,
            "rejected_medal": self.rejected_medal,
            "rejected_blocked": self.rejected_blocked,
            "missing_flag": self.missing_flag,
            "secondary_recorded": self.secondary_recorded,
            "pending_count": sum(item.get("published") is False for item in self.store.records),
            "blc_events": self.blc_events,
            "last_event": self.last_event,
            "record_count": len(self.store.records),
            "flag": self.config["flag"],
            "blocked_words": self.config["blocked_words"],
            "max_chars": self.config["max_chars"],
            "min_medal_level": self.config["min_medal_level"],
            "last_error": self.last_error,
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
    store = RecordStore(config["max_records"])
    app = FlagRecordApp(store, config)
    @web.middleware
    async def no_cache(request, handler):
        response = await handler(request)
        if request.path in ("/admin", "/overlay/wish-wall", "/overlay/flag-records") or request.path.startswith("/api/"):
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

    async def records(_):
        published_only = _.query.get("published") == "1"
        return web.json_response({"records": store.snapshot(published_only=published_only)})

    async def update_config(request):
        data = await request.json()
        flag = str(data.get("flag") or "").strip()[:32]
        title = str(data.get("wall_title") or "").strip()[:20]
        if not flag or not title:
            raise web.HTTPBadRequest(text="激活词和展示抬头不能为空")
        config["flag"] = flag
        secondary_source = data.get("secondary_flags", config["secondary_flags"])
        if not isinstance(secondary_source, list):
            raise web.HTTPBadRequest(text="secondary_flags 格式不正确")
        secondary_flags = []
        seen_secondary = set()
        for value in secondary_source[:50]:
            word = str(value or "").replace("\r", "").replace("\n", "").strip()[:32]
            folded = word.casefold()
            if word and folded not in seen_secondary:
                secondary_flags.append(word)
                seen_secondary.add(folded)
        config["secondary_flags"] = secondary_flags
        config["secondary_auto_publish"] = data.get("secondary_auto_publish") is True
        config["blocked_words"] = str(data.get("blocked_words", config["blocked_words"])).replace("\r", "").replace("\n", "")[:500]
        color = str(data.get("font_color") or "").strip()
        stroke_color = str(data.get("stroke_color") or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise web.HTTPBadRequest(text="font_color 格式不正确")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", stroke_color):
            raise web.HTTPBadRequest(text="stroke_color 格式不正确")
        config["wall_title"] = title
        separator = str(data.get("entry_separator", config["entry_separator"])).replace("\r", "").replace("\n", "")
        config["entry_separator"] = separator[:12]
        layout_mode = str(data.get("layout_mode") or "vertical")
        if layout_mode not in ("vertical", "horizontal"):
            raise web.HTTPBadRequest(text="layout_mode 格式不正确")
        config["layout_mode"] = layout_mode
        scroll_axis = str(data.get("scroll_axis") or "vertical")
        if scroll_axis not in ("vertical", "horizontal"):
            raise web.HTTPBadRequest(text="scroll_axis 格式不正确")
        config["scroll_axis"] = scroll_axis
        config["font_color"] = color.lower()
        config["stroke_color"] = stroke_color.lower()
        config["stroke_enabled"] = data.get("stroke_enabled") is True
        try:
            config["stroke_width"] = max(0.0, min(6.0, float(data.get("stroke_width", config["stroke_width"]))))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="stroke_width 格式不正确")
        for key, low, high in (("max_chars", 0, 500), ("min_medal_level", 0, 1000), ("scroll_speed", 10, 200), ("font_size", 12, 96)):
            try:
                config[key] = max(low, min(high, int(data.get(key, config[key]))))
            except (TypeError, ValueError):
                raise web.HTTPBadRequest(text=f"{key} 格式不正确")
        save_json(CONFIG_PATH, config)
        settings = app.public_settings()
        await app.broadcast({"type": "settings_updated", "settings": settings})
        return web.json_response({"ok": True, "settings": settings})

    async def test(request):
        data = await request.json()
        raw_text = str(data.get("text") or f"{config['flag']}这是一条测试心愿")
        record, reason = await app.accept_danmaku(
            str(data.get("uid") or "test"),
            str(data.get("name") or "测试观众"),
            raw_text,
            data.get("medal_level"),
        )
        return web.json_response({"ok": record is not None, "reason": reason, "record": record})

    async def delete_record(request):
        record_id = request.match_info["record_id"]
        deleted = await store.delete(record_id)
        if not deleted:
            raise web.HTTPNotFound()
        await app.broadcast({"type": "record_deleted", "id": record_id})
        return web.json_response({"ok": True})

    async def publish_record(request):
        record = await store.publish(request.match_info["record_id"])
        if record is None:
            raise web.HTTPNotFound()
        await app.broadcast({"type": "record_published", "record": record})
        return web.json_response({"ok": True, "record": record})

    async def socket_handler(request):
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        app.clients.add(socket)
        published_only = request.query.get("view") == "overlay"
        await socket.send_str(json.dumps({"type": "snapshot", "records": store.snapshot(published_only=published_only), "settings": app.public_settings()}, ensure_ascii=False))
        try:
            async for _ in socket:
                pass
        finally:
            app.clients.discard(socket)
        return socket

    server.router.add_get("/", index)
    server.router.add_get("/admin", admin)
    server.router.add_get("/overlay/wish-wall", overlay)
    server.router.add_get("/overlay/flag-records", overlay)
    server.router.add_get("/api/status", status)
    server.router.add_get("/api/records", records)
    server.router.add_post("/api/config", update_config)
    server.router.add_post("/api/test", test)
    server.router.add_post("/api/records/{record_id}/publish", publish_record)
    server.router.add_delete("/api/records/{record_id}", delete_record)
    server.router.add_get("/ws/records", socket_handler)

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
