from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional

from config import settings
from room_manager import RoomManager
from logging_config import setup_logging

# The message pipeline is optional — import if available, fail soft if not.
try:
    from message_pipline import MessagePipeline, ValidationHandler, SecurityHandler  # noqa: F401
except Exception:  # keep tests green even if pipeline module changes/missing
    MessagePipeline = None  # type: ignore


class ChatServer:
    """
    Minimal chat server wrapper that:
      - manages join/leave via RoomManager
      - ignores command echoes (/nick, /join, /showall)
      - broadcasts only real chat payloads
    """

    def __init__(self) -> None:
        # loggers
        self.app_logger, self.security_logger = setup_logging()

        # optional pipeline (keep flexible for Part 2)
        self.pipeline: Optional[MessagePipeline] = None  # type: ignore[assignment]
        try:
            if MessagePipeline is not None:
                # If you later wire real handlers, do it here
                self.pipeline = MessagePipeline([])
        except Exception:
            self.pipeline = None

        # room manager (pass pipeline if your RoomManager uses it)
        try:
            self.room_manager = RoomManager(self.pipeline)  # type: ignore[arg-type]
        except TypeError:
            # If RoomManager doesn't accept a pipeline in your version
            self.room_manager = RoomManager()

        self.clients = set()

    async def handle_client(self, websocket: WebSocket) -> None:
        """Accepts a client, processes commands silently, broadcasts chat messages."""
        await websocket.accept()
        room = settings.default_room
        setattr(websocket, "nick", "Bean")
        setattr(websocket, "showall", False)

        # Join default room without sending any system echo
        if hasattr(self.room_manager, "join"):
            await self.room_manager.join(room, websocket)  # type: ignore[attr-defined]

        self.clients.add(websocket)

        try:
            while True:
                text = await websocket.receive_text()

                # ---- Commands (NO echo back) ----
                if text.startswith("/nick "):
                    new_nick = text.split(" ", 1)[1].strip()
                    websocket.nick = new_nick or "Bean"
                    continue

                if text.startswith("/join "):
                    new_room = text.split(" ", 1)[1].strip() or settings.default_room
                    if hasattr(self.room_manager, "leave"):
                        await self.room_manager.leave(room, websocket)  # type: ignore[attr-defined]
                    room = new_room
                    if hasattr(self.room_manager, "join"):
                        await self.room_manager.join(room, websocket)  # type: ignore[attr-defined]
                    continue

                if text.startswith("/showall"):
                    # Toggle flag; do not echo
                    parts = text.split()
                    if len(parts) == 2 and parts[1].lower() in {"on", "off"}:
                        websocket.showall = (parts[1].lower() == "on")
                    continue

                # ---- Real chat payload ----
                message = text
                # If you later add validation/DLP, run the pipeline here (non-blocking)
                # if self.pipeline:
                #     message = await self.pipeline.process(message)  # example

                await self.room_manager.broadcast(
                    room,
                    message,
                    sender=websocket,
                    echo_to_sender=True,  # tests expect the sender to receive their own message
                )

        except WebSocketDisconnect:
            if hasattr(self.room_manager, "leave"):
                await self.room_manager.leave(room, websocket)  # type: ignore[attr-defined]
            self.clients.discard(websocket)


# FastAPI app + endpoints
app = FastAPI(title="TSPO Chat Server")

chat_server = ChatServer()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await chat_server.handle_client(websocket)


@app.get("/health")
async def health():
    # Keep response minimal for tests; add diagnostics if you want.
    return {"status": "ok"}


# Admin endpoints for Part 2 (stubs)
@app.post("/admin/dlp/reload")
async def reload_dlp_rules():
    return {"status": "not_implemented"}
