# server/app.py
# FastAPI + WebSocket server with simple room routing.
# Wire format for chat messages: "room|nick|text"
# - On each message, we update the sender's current room/nick and broadcast only to that room.
# - Also supports a simple slash command: "/join <room>"

import os
import re
import asyncio
from typing import Optional, Set, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

TAG_RE = re.compile(r"^([^|]{1,64})\|([^|]{1,64})\|(.*)$")  # room|nick|text

app = FastAPI(title="TSPO Chat – Rooms")

# --- Room manager (Observer/PubSub-like) ---
class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def join(self, room: str, ws: WebSocket):
        async with self.lock:
            self.rooms.setdefault(room, set()).add(ws)

    async def leave(self, room: str, ws: WebSocket):
        async with self.lock:
            if room in self.rooms:
                self.rooms[room].discard(ws)
                if not self.rooms[room]:
                    self.rooms.pop(room, None)

    async def broadcast(self, room: str, message: str, exclude: Optional[WebSocket] = None):
        # send only to members of the room
        targets: Set[WebSocket] = set()
        async with self.lock:
            targets = set(self.rooms.get(room, set()))
        to_remove = []
        for c in targets:
            if c is exclude:
                continue
            try:
                await c.send_text(message)
            except Exception:
                to_remove.append(c)
        # cleanup broken sockets
        if to_remove:
            async with self.lock:
                for c in to_remove:
                    for rset in self.rooms.values():
                        rset.discard(c)

rooms = RoomManager()

# Per-connection state: current room & nick
DEFAULT_ROOM = os.getenv("DEFAULT_ROOM", "lobby")
client_state: Dict[WebSocket, Dict[str, str]] = {}
state_lock = asyncio.Lock()

@app.get("/health")
async def health():
    # basic liveness (and rough counts)
    async with rooms.lock:
        total_clients = sum(len(s) for s in rooms.rooms.values())
        room_names = list(rooms.rooms.keys())
    return JSONResponse({"status": "ok", "total_clients": total_clients, "rooms": room_names})

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    # set initial state
    async with state_lock:
        client_state[ws] = {"room": DEFAULT_ROOM, "nick": "anon"}
    await rooms.join(DEFAULT_ROOM, ws)
    # announce system message (optional)
    await rooms.broadcast(DEFAULT_ROOM, f"{DEFAULT_ROOM}|system|[joined anon]", exclude=None)

    try:
        while True:
            msg = await ws.receive_text()

            # handle slash command: /join <room>
            if msg.startswith("/join "):
                new_room = msg.split(maxsplit=1)[1].strip()[:64] or DEFAULT_ROOM
                async with state_lock:
                    old_room = client_state[ws]["room"]
                    nick = client_state[ws]["nick"]
                    if new_room != old_room:
                        client_state[ws]["room"] = new_room
                        await rooms.leave(old_room, ws)
                        await rooms.join(new_room, ws)
                # optional system notifications
                await rooms.broadcast(old_room, f"{old_room}|system|[left {nick}]", exclude=None)
                await rooms.broadcast(new_room, f"{new_room}|system|[joined {nick}]", exclude=None)
                continue

            # parse room|nick|text (updates the sender's current room/nick)
            m = TAG_RE.match(msg)
            if m:
                room, nick, text = m.groups()
                room = room.strip()[:64] or DEFAULT_ROOM
                nick = nick.strip()[:64] or "anon"
                async with state_lock:
                    # if room changed, move the socket between room sets
                    old_room = client_state[ws]["room"]
                    client_state[ws]["room"] = room
                    client_state[ws]["nick"] = nick
                if room != old_room:
                    await rooms.leave(old_room, ws)
                    await rooms.join(room, ws)
                    # optional system notices
                    await rooms.broadcast(old_room, f"{old_room}|system|[left {nick}]", exclude=None)
                    await rooms.broadcast(room, f"{room}|system|[joined {nick}]", exclude=None)

                # broadcast only to the current room
                await rooms.broadcast(room, f"{room}|{nick}|{text}", exclude=ws)
            else:
                # untagged: deliver to sender's current room using last known nick
                async with state_lock:
                    room = client_state[ws]["room"]
                    nick = client_state[ws]["nick"]
                await rooms.broadcast(room, f"{room}|{nick}|{msg}", exclude=ws)

    except WebSocketDisconnect:
        pass
    finally:
        # cleanup
        async with state_lock:
            st = client_state.pop(ws, {"room": DEFAULT_ROOM, "nick": "anon"})
        await rooms.leave(st["room"], ws)
        # announce departure (optional)
        await rooms.broadcast(st["room"], f"{st['room']}|system|[disconnected {st['nick']}]", exclude=None)

if __name__ == "__main__":
    # listen on 0.0.0.0 so other machines can reach us
    port = int(os.getenv("PORT", "8090"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
