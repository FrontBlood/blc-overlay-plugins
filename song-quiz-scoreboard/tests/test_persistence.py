import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from aiohttp import web


ROOT = Path(__file__).resolve().parents[1]


async def request(url, method="GET", payload=None, timeout=10):
    deadline = asyncio.get_running_loop().time() + timeout
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    while asyncio.get_running_loop().time() < deadline:
        try:
            def send():
                req = urllib.request.Request(url, data=body, method=method)
                if body is not None:
                    req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=1) as response:
                    return response.status, dict(response.headers), response.read()
            return await asyncio.to_thread(send)
        except Exception:
            await asyncio.sleep(0.1)
    raise AssertionError(f"HTTP service did not respond: {url}")


async def run_test():
    connections = 0

    async def unstable_blc(request):
        nonlocal connections
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        connections += 1
        await socket.send_str(json.dumps({"cmd": "BLC_INIT"}))
        await asyncio.sleep(0.2)
        await socket.close()
        return socket

    fake_blc = web.Application()
    fake_blc.router.add_get("/api/plugin/websocket", unstable_blc)
    runner = web.AppRunner(fake_blc)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 12554).start()
    env = os.environ.copy()
    env.update(BLC_PORT="12554", BLC_TOKEN="persistence-test")
    process = subprocess.Popen(
        [sys.executable, "main.py"], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        status_code, headers, _ = await request("http://127.0.0.1:18454/overlay/song-score")
        assert status_code == 200
        assert "no-store" in headers.get("Cache-Control", "")
        await request("http://127.0.0.1:18454/api/session/start", method="POST")
        _, _, result = await request(
            "http://127.0.0.1:18454/api/test", method="POST",
            payload={"uid": "regression-user", "name": "回归测试", "text": "+2", "medal_level": 0},
        )
        assert json.loads(result)["player"]["score"] == 2
        deadline = asyncio.get_running_loop().time() + 8
        while connections < 2 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)
        assert connections >= 2, "BLC websocket was not reconnected"
        _, _, scores = await request("http://127.0.0.1:18454/api/scores")
        assert json.loads(scores)["players"][0]["score"] == 2
        assert process.poll() is None, "HTTP service exited after BLC disconnect"
    finally:
        process.terminate()
        await asyncio.to_thread(process.wait, 5)
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(run_test())
    print("scoreboard persistence and scoring regression test passed")
