
import asyncio
from typing import Dict, Set, Protocol, Optional
from fastapi import WebSocket
from message_pipline import MessagePipeline  # optional: kept for future use

# Manages rooms and message fan-out

class MessageObserver(Protocol):
    async def on_message(self, room: str, message: str, sender) -> None: ...
    async def on_join(self, room: str, client) -> None: ...
    async def on_leave(self, room: str, client) -> None: ...


class RoomManager:
    def __init__(self, pipeline: Optional[MessagePipeline] = None):
        self.pipeline = pipeline
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def join(self, room: str, ws: WebSocket) -> None:
        """Add a websocket to a room."""
        async with self.lock:
            self.rooms.setdefault(room, set()).add(ws)

    async def leave(self, room: str, ws: WebSocket) -> None:
        """Remove a websocket from a room (and delete empty rooms)."""
        async with self.lock:
            members = self.rooms.get(room)
            if not members:
                return
            members.discard(ws)
            if not members:
                del self.rooms[room]

    async def broadcast(
        self,
        room: str,
        text: str,
        *,
        sender: WebSocket | None = None,
        echo_to_sender: bool = True,
    ) -> None:
        """Send text to all members of a room (optionally skip the sender)."""
        # snapshot recipients outside the send loop to avoid holding the lock
        async with self.lock:
            recipients = list(self.rooms.get(room, set()))

        for ws in recipients:
            if not echo_to_sender and ws is sender:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                # cleanup dead sockets on failure
                async with self.lock:
                    bucket = self.rooms.get(room)
                    if bucket:
                        bucket.discard(ws)
                        if not bucket:
                            self.rooms.pop(room, None)

    async def get_room_list(self) -> Dict[str, int]:
        """Return rooms with member counts."""
        async with self.lock:
            return {room: len(members) for room, members in self.rooms.items()}

    async def get_room_info(self, room: str) -> Dict:
        """Return detailed info for a room."""
        async with self.lock:
            members = self.rooms.get(room)
            if not members:
                return {"exists": False}
            return {
                "exists": True,
                "name": room,
                "member_count": len(members),
                "members": [getattr(c, "nick", "anon") for c in members],
            }