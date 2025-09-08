# server/room_manager.py
import asyncio
from dataclasses import dataclass
from typing import Dict, Set, Protocol, Optional, List
from fastapi import WebSocket
from message_pipline import MessagePipeline  # keep your filename

# ---------- Data models ----------
@dataclass
class User:
    user_id: str
    nickname: str

# ---------- Observer protocol ----------
class MessageObserver(Protocol):
    async def on_message(self, room: str, message: str, sender: WebSocket) -> None: ...
    async def on_join(self, room: str, client: WebSocket) -> None: ...
    async def on_leave(self, room: str, client: WebSocket) -> None: ...

# ---------- Room manager ----------
class RoomManager:
    def __init__(self, pipeline: Optional[MessagePipeline] = None):
        self.pipeline = pipeline
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self.users: Dict[str, User] = {}
        self.ws_to_user: Dict[WebSocket, str] = {}
        self.lock = asyncio.Lock()
        self.observers: List[MessageObserver] = []

    async def register_user(self, user: User) -> None:
        """Add/update user in memory."""
        async with self.lock:
            self.users[user.user_id] = user

    async def get_user(self, user_id: str) -> Optional[User]:
        async with self.lock:
            return self.users.get(user_id)

    async def ensure_room(self, name: str) -> None:
        """Create the room if missing."""
        async with self.lock:
            self.rooms.setdefault(name, set())

    async def join(self, room: str, ws: WebSocket, user: User) -> None:
        """Add ws to room and bind to user."""
        async with self.lock:
            self.rooms.setdefault(room, set()).add(ws)
            self.ws_to_user[ws] = user.user_id
            setattr(ws, "nick", user.nickname)  # for UI lists

        # notify observers outside the lock
        for obs in self.observers:
            try:
                await obs.on_join(room, ws)
            except Exception:
                pass

    async def leave(self, room: str, ws: WebSocket) -> None:
        """Remove ws from room; cleanup empty room."""
        async with self.lock:
            if room in self.rooms:
                self.rooms[room].discard(ws)
                if not self.rooms[room]:
                    self.rooms.pop(room, None)
            self.ws_to_user.pop(ws, None)

        # notify observers outside the lock
        for obs in self.observers:
            try:
                await obs.on_leave(room, ws)
            except Exception:
                pass

    async def broadcast(
        self,
        room: str,
        text: str,
        *,
        sender: Optional[WebSocket] = None,
        echo_to_sender: bool = True,
    ) -> None:
        """
        Send a message to all members of a room.
        NOTE:
        - Do NOT mutate 'text' to prepend nickname here.
          The caller (e.g., app/ChatServer) should build the final payload
          (JSON or plain text) before calling broadcast.
        """
        # snapshot members under lock
        async with self.lock:
            members = list(self.rooms.get(room, set()))

        # optional pipeline
        if self.pipeline:
            try:
                text = await self.pipeline.process(text, room=room, sender=sender)
                if text is None:
                    return  # Block the message if pipeline returns None
            except Exception:
                # fail open on pipeline errors
                pass

        dead: List[WebSocket] = []
        for ws in members:
            if not echo_to_sender and ws is sender:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)

        # cleanup dead sockets under lock
        if dead:
            async with self.lock:
                for ws in dead:
                    if room in self.rooms:
                        self.rooms[room].discard(ws)
                        if not self.rooms[room]:
                            self.rooms.pop(room, None)
                    self.ws_to_user.pop(ws, None)

        # observer hook
        for obs in self.observers:
            try:
                if sender is not None:
                    await obs.on_message(room, text, sender)
            except Exception:
                pass

    async def get_room_list(self) -> Dict[str, int]:
        async with self.lock:
            return {room: len(members) for room, members in self.rooms.items()}

    async def get_room_info(self, room: str) -> Dict:
        async with self.lock:
            if room not in self.rooms:
                return {"exists": False}
            members = self.rooms[room]
            return {
                "exists": True,
                "name": room,
                "member_count": len(members),
                "members": [getattr(c, "nick", "anon") for c in members],
            }
