import asyncio
from typing import Dict, Set, Protocol, Optional
from fastapi import WebSocket
from message_pipline import MessagePipeline

# Responsible for managing rooms and broadcasting messages

class MessageObserver(Protocol):
    async def on_message(self, room: str, message: str, sender) -> None:
        """Called when a message is broadcast to a room"""
        pass

    async def on_join(self, room: str, client) -> None:
        """Called when a client joins a room"""
        pass

    async def on_leave(self, room: str, client) -> None:
        """Called when a client leaves a room"""
        pass


class RoomManager:
    def __init__(self, pipeline: Optional[MessagePipeline] = None):
        self.pipeline = pipeline
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self.lock = asyncio.Lock()  # ensure safe concurrent access

    async def broadcast(
        self,
        room: str,
        text: str,
        *,
        sender: WebSocket | None = None,
        echo_to_sender: bool = True,
    ):
        """Send a message to all members of a room"""
        for ws in list(self.rooms.get(room, set())):
            if not echo_to_sender and ws is sender:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                # cleanup dead sockets
                self.rooms[room].discard(ws)

    async def get_room_list(self) -> Dict[str, int]:
        """Returns available rooms with member counts"""
        async with self.lock:
            return {
                room: len(members)
                for room, members in self.rooms.items()
            }

    async def get_room_info(self, room: str) -> Dict:
        """Get detailed information about a specific room"""
        async with self.lock:
            if room not in self.rooms:
                return {"exists": False}
            return {
                "exists": True,
                "name": room,
                "member_count": len(self.rooms[room]),
                "members": [getattr(c, "nick", "anon") for c in self.rooms[room]],
            }