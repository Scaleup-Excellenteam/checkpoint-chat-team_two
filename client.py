import asyncio, os
import websockets

# Try proxy first (works per your curl), then direct IP as fallback
SERVER_URLS = [
    os.getenv("SERVER_URL", "ws://127.0.0.1:8099/ws"),
    "ws://172.20.10.13:8080/ws",
]
NAME = os.getenv("NAME", "Lior")

async def run_chat(url):
    print(f"connecting to {url} as {NAME} ...")
    async with websockets.connect(
        url,
        open_timeout=6,      # fail fast if unreachable
        ping_interval=20,    # keepalive
        ping_timeout=20,
        max_queue=32,
    ) as ws:
        print("connected ✓")
        # tell server who we are (your server supports room|nick|text)
        await ws.send(f"lobby|{NAME}|[joined]")
        async for msg in ws:
            print("<<", msg)

async def main():
    last_err = None
    for url in SERVER_URLS:
        try:
            await run_chat(url)
            return
        except (asyncio.TimeoutError, OSError, websockets.InvalidURI) as e:
            print(f"failed to connect to {url}: {e}")
            last_err = e
    raise SystemExit(f"all endpoints failed: {last_err}")

if __name__ == "__main__":
    asyncio.run(main())
