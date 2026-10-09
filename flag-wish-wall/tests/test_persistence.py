import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from aiohttp import web


ROOT = Path(__file__).resolve().parents[1]


async def wait_for_http(url, timeout=10):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            return await asyncio.to_thread(lambda: urllib.request.urlopen(url, timeout=1).read())
        except Exception:
            await asyncio.sleep(0.1)
    raise AssertionError(f"HTTP service did not become ready: {url}")


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
    await web.TCPSite(runner, "127.0.0.1", 12553).start()

    env = os.environ.copy()
    env.update(BLC_PORT="12553", BLC_TOKEN="persistence-test")
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        await wait_for_http("http://127.0.0.1:18453/api/status")
        deadline = asyncio.get_running_loop().time() + 8
        while connections < 2 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)
        assert connections >= 2, "BLC websocket was not reconnected"
        status = json.loads((await wait_for_http("http://127.0.0.1:18453/api/status")).decode("utf-8"))
        assert "record_count" in status
        assert process.poll() is None, "HTTP service exited after BLC disconnect"
    finally:
        process.terminate()
        await asyncio.to_thread(process.wait, 5)
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(run_test())
    print("persistence test passed")
