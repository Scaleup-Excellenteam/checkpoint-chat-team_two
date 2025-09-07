# interactive_client.py
# Interactive WebSocket chat client with local rooms + slash commands.
# Wire format: "room|nick|text"
#
# Commands:
#   /join <room>     switch current room (default: lobby)
#   /nick <name>     change nickname (default: anon)
#   /showall on|off  show messages from other rooms (default: off)
#   /quit            exit
#
# Usage:
#   python interactive_client.py --url ws://<SERVER-IP>:8080/ws --nick alice --room lobby
#   (or via env: SERVER_URL, NICK, ROOM, SHOW_OTHER_ROOMS)

import os
import re
import sys
import argparse
import asyncio
import signal
import websockets

TAG_RE = re.compile(r"^([^|]{1,64})\|([^|]{1,64})\|(.*)$")  # room|nick|text

def parse_args():
    p = argparse.ArgumentParser(description="Interactive WS chat client")
    p.add_argument("--url", default=os.getenv("SERVER_URL", "ws://localhost:8080/ws"))
    p.add_argument("--nick", default=os.getenv("NICK", "anon"))
    p.add_argument("--room", default=os.getenv("ROOM", "lobby"))
    p.add_argument("--showall", default=os.getenv("SHOW_OTHER_ROOMS", "off"),
                   help="on/off: show messages from other rooms")
    p.add_argument("--ping-interval", type=float, default=20.0)
    p.add_argument("--ping-timeout", type=float, default=20.0)
    p.add_argument("--max-backoff", type=float, default=5.0)
    return p.parse_args()

class State:
    def __init__(self, url, nick, room, show_all, max_backoff, ping_interval, ping_timeout):
        self.url = url
        self.nick = nick[:64] or "anon"
        self.room = room[:64] or "lobby"
        self.show_all = str(show_all).lower() in ("1","true","yes","on")
        self.running = True
        self.max_backoff = max_backoff
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

def print_help():
    print("commands:")
    print("  /join <room>     switch room")
    print("  /nick <name>     change nickname")
    print("  /showall on|off  toggle showing other rooms")
    print("  /quit            exit")
    print("type a message and press enter to send")

async def read_stdin():
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            await asyncio.sleep(0.05)
            continue
        yield line.rstrip("\r\n")

async def receiver(ws, state: State):
    while state.running:
        try:
            msg = await ws.recv()
        except websockets.ConnectionClosed:
            print("disconnected from server")
            break
        except Exception as e:
            print(f"receive error: {e}")
            break

        room = None; nick = None; text = msg
        m = TAG_RE.match(msg)
        if m:
            room, nick, text = m.groups()

        if room is None:
            print(text)
        else:
            if room == state.room or state.show_all:
                prefix = f"[{room}]"
                if nick:
                    prefix += f" {nick}:"
                print(f"{prefix} {text}")

async def handle_command(cmd: str, state: State):
    parts = cmd.split()
    c = parts[0].lower()
    if c == "/join":
        if len(parts) < 2: return print("usage: /join <room>")
        state.room = parts[1][:64] or "lobby"
        print(f"(switched room to '{state.room}')")
    elif c == "/nick":
        if len(parts) < 2: return print("usage: /nick <name>")
        state.nick = parts[1][:64] or "anon"
        print(f"(nick set to '{state.nick}')")
    elif c == "/showall":
        if len(parts) < 2 or parts[1].lower() not in ("on","off"):
            return print("usage: /showall on|off")
        state.show_all = (parts[1].lower() == "on")
        print(f"(showall is now {'on' if state.show_all else 'off'})")
    elif c == "/quit":
        state.running = False
        print("bye")
    else:
        print_help()

async def sender(ws, state: State):
    print_help()
    print(f"connected → room={state.room}, nick={state.nick}, showall={'on' if state.show_all else 'off'}")
    async for line in read_stdin():
        if not state.running:
            break
        if not line:
            continue
        if line.startswith("/"):
            await handle_command(line, state)
            if not state.running: break
            continue
        wire = f"{state.room}|{state.nick}|{line}"
        try:
            await ws.send(wire)
        except Exception as e:
            print(f"send error: {e}")
            break

async def connect_and_run(state: State):
    backoff = 0.5
    while state.running:
        try:
            async with websockets.connect(
                state.url,
                ping_interval=state.ping_interval,
                ping_timeout=state.ping_timeout,
                max_size=2**20
            ) as ws:
                backoff = 0.5
                recv_t = asyncio.create_task(receiver(ws, state))
                send_t = asyncio.create_task(sender(ws, state))
                done, pending = await asyncio.wait({recv_t, send_t}, return_when=asyncio.FIRST_COMPLETED)
                for t in pending:
                    t.cancel()
        except Exception as e:
            print(f"connect error: {e}")
        if state.running:
            print(f"reconnecting in {backoff:.1f}s ...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, state.max_backoff)

def main():
    args = parse_args()
    state = State(
        url=args.url,
        nick=args.nick,
        room=args.room,
        show_all=args.showall,
        max_backoff=args.max_backoff,
        ping_interval=args.ping_interval,
        ping_timeout=args.ping_timeout,
    )
    signal.signal(signal.SIGINT, lambda *_: setattr(state, "running", False))
    asyncio.run(connect_and_run(state))

if __name__ == "__main__":
    main()
