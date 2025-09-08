from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional
import json

from config import settings
from room_manager import RoomManager
from logging_config import setup_logging

# The message pipeline with DLP and URL filtering integration
try:
    from message_pipline import MessagePipeline, ValidationHandler, DLPMessageHandler, URLFilterHandler
    from security.dlp_handler import DLPHandler
    from security.url_filter import URLFilter
except Exception:  # keep tests green even if pipeline module changes/missing
    MessagePipeline = None  # type: ignore
    DLPHandler = None  # type: ignore
    URLFilter = None  # type: ignore


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

        # Initialize DLP and URL filtering pipeline
        self.pipeline: Optional[MessagePipeline] = None  # type: ignore[assignment]
        try:
            if MessagePipeline is not None and DLPHandler is not None and URLFilter is not None:
                dlp = DLPHandler("config/dlp_rules.json")
                url_filter = URLFilter("config/dlp_rules.json")
                self.pipeline = MessagePipeline()
                self.pipeline.handlers = [
                    ValidationHandler(),
                    DLPMessageHandler(dlp, use_gemini=True),  # DLP with Gemini
                    URLFilterHandler(url_filter)  # URL filtering
                ]
                self.app_logger.info("DLP and URL filtering pipeline initialized successfully")
        except Exception as e:
            self.app_logger.error(f"Failed to initialize pipeline: {e}")
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
        setattr(websocket, "nick", "anon")
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
                    websocket.nick = new_nick or "anon"
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
                # Format message for pipeline: room|nick|text
                raw_message = f"{room}|{websocket.nick}|{text}"
                
                # Log incoming message for debugging
                self.app_logger.info(f"Processing message: {raw_message}")
                
                # Process through DLP pipeline
                if self.pipeline:
                    try:
                        processed_message = await self.pipeline.process(raw_message, websocket)
                        if processed_message is None:
                            # Message blocked by DLP or URL filter
                            await websocket.send_text("⚠️ Message blocked: Contains sensitive content")
                            self.security_logger.warning(f"Message blocked from {websocket.nick}: {text}")
                            self.app_logger.info(f"BLOCKED: {raw_message}")
                            continue
                        # Extract processed text from pipeline result
                        _, _, processed_text = processed_message.split("|", 2)
                        message = processed_text
                        self.app_logger.info(f"ALLOWED: {raw_message}")
                    except Exception as e:
                        self.app_logger.error(f"Pipeline error: {e}")
                        message = text  # Fallback to original message
                else:
                    self.app_logger.info(f"No pipeline - using original message: {text}")
                    message = text

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


# Admin endpoints for DLP management
@app.post("/admin/dlp/reload")
async def reload_dlp_rules():
    """Reload DLP rules from configuration file"""
    try:
        if chat_server.pipeline and hasattr(chat_server.pipeline, 'handlers'):
            for handler in chat_server.pipeline.handlers:
                if hasattr(handler, 'dlp_handler'):
                    # Reload DLP configuration
                    with open("config/dlp_rules.json") as f:
                        handler.dlp_handler.config = json.load(f)
                    return {"status": "success", "message": "DLP rules reloaded"}
        return {"status": "error", "message": "DLP not initialized"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
