from __future__ import annotations

import re
import json
from typing import Optional, Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from room_manager import RoomManager
from logging_config import setup_logging

# The message pipeline with DLP and URL filtering integration
try:
    
    from security.dlp_handler import DLPHandler, DLPMessageHandler
    from message_pipline import MessagePipeline, ValidationHandler, DLPMessageHandler, URLFilterHandler
    from security.url_filter import URLFilter
except Exception:  # keep tests green even if pipeline module changes/missing
    MessagePipeline = None  # type: ignore
    DLPHandler = None  # type: ignore
    URLFilter = None  # type: ignore

KNOWN_ROOMS: Set[str] = {"lobby"}
# --- In-memory stores (POC only; replace with DB/JWT in real app) ---
USERS: Dict[str, Dict[str, int | str]] = {}  # nickname -> {"password": str, "user_id": int}
ONLINE: Dict[str, Dict[str, str]] = {}       # nick -> {"room": "<room>"}
_next_uid = 1


class Credentials(BaseModel):
    nickname: str
    password: str


class RoomIn(BaseModel):
    name: str


class ChatServer:
    """
    Minimal chat server wrapper that:
      - manages join/leave via RoomManager
      - supports optional DLP pipeline
      - supports slash-commands: /nick, /join, /showall (no echo)
      - broadcasts chat payloads as JSON envelopes compatible with the frontend
    """
    username: str
    password: str

    def __init__(self) -> None:
        # loggers
        self.app_logger, self.security_logger = setup_logging()

        # Initialize DLP pipeline (optional)
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

        self.clients: Set[WebSocket] = set()

    # --- ONLINE helpers ---
    def _online_put(self, nick: str, room: str) -> None:
        if nick:
            ONLINE[nick] = {"room": room}

    def _online_rename(self, old: str, new: str, room: str) -> None:
        if old:
            ONLINE.pop(old, None)
        if new:
            ONLINE[new] = {"room": room}

    def _online_move(self, nick: str, room: str) -> None:
        if nick:
            ONLINE[nick] = {"room": room}

    def _online_drop(self, nick: str) -> None:
        if nick:
            ONLINE.pop(nick, None)

    # --- WS entrypoint core ---
    async def handle_client(self, websocket: WebSocket, initial_room: Optional[str] = None, initial_nick: Optional[str] = None) -> None:
        """Accepts a client, processes commands silently, broadcasts chat messages as JSON envelopes."""
        await websocket.accept()

        # resolve initial state (room & nickname)
        room = (initial_room or settings.default_room or "lobby").strip() or "lobby"
        nick = (initial_nick or "Bean").strip() or "Bean"

        # attach attributes used by slash-commands
        setattr(websocket, "nick", nick)
        setattr(websocket, "showall", False)

        # join initial room (no echo back to the same client)
        if hasattr(self.room_manager, "join"):
            await self.room_manager.join(room, websocket)  # type: ignore[attr-defined]

        # track online presence
        self._online_put(nick, room)
        self.clients.add(websocket)

        # optional: announce join to the room as system message
        try:
            join_evt = json.dumps({"type": "system", "event": "joined", "nickname": nick})
            await self.room_manager.broadcast(room, join_evt, sender=None, echo_to_sender=True)
        except Exception:
            # don't fail connection on optional announce
            pass

        try:
            while True:
                text = await websocket.receive_text()

                # --- Handle JSON control frames (ping/chat) if present ---
                obj = None
                try:
                    obj = json.loads(text)
                except Exception:
                    obj = None

                if isinstance(obj, dict) and "type" in obj:
                    typ = obj.get("type")
                    if typ == "ping":
                        # keep-alive
                        #await websocket.send_text(json.dumps({"type": "system", "event": "pong"}))
                        continue
                    if typ == "chat":
                        incoming_text = str(obj.get("text", ""))
                        # pipeline input format remains room|nick|text to preserve your logic
                        raw_message = f"{room}|{websocket.nick}|{incoming_text}"
                        if self.pipeline:
                            try:
                                processed = await self.pipeline.process(raw_message, websocket)
                                if processed is None:
                                    await websocket.send_text(
                                        json.dumps(
                                            {
                                                "type": "system",
                                                "event": "blocked",
                                                "nickname": websocket.nick,
                                            }
                                        )
                                    )
                                    self.security_logger.warning(
                                        f"DLP blocked message from {websocket.nick}: {incoming_text}"
                                    )
                                    continue
                                _, _, processed_text = processed.split("|", 2)
                                outgoing_text = processed_text
                            except Exception as e:
                                self.app_logger.error(f"Pipeline error: {e}")
                                outgoing_text = incoming_text
                        else:
                            outgoing_text = incoming_text

                        # broadcast as JSON envelope compatible with the frontend
                        payload = json.dumps(
                            {"type": "chat", "nickname": websocket.nick, "text": outgoing_text}
                        )
                        await self.room_manager.broadcast(
                            room, payload, sender=websocket, echo_to_sender=True
                        )
                        continue

                # --- Slash-commands (text mode), no echo back ---
                if text.startswith("/nick "):
                    new_nick = text.split(" ", 1)[1].strip() or "Bean"
                    old_nick = getattr(websocket, "nick", "Bean")
                    websocket.nick = new_nick
                    self._online_rename(old_nick, new_nick, room)
                    # optional announce rename
                    try:
                        evt = json.dumps({"type": "system", "event": "renamed", "nickname": new_nick})
                        await self.room_manager.broadcast(room, evt, sender=None, echo_to_sender=True)
                    except Exception:
                        pass
                    continue

                if text.startswith("/join "):
                    new_room = text.split(" ", 1)[1].strip() or settings.default_room or "lobby"
                    # leave old, join new
                    if hasattr(self.room_manager, "leave"):
                        await self.room_manager.leave(room, websocket)  # type: ignore[attr-defined]
                    room = new_room
                    self._remember_room(room)
                    if hasattr(self.room_manager, "join"):
                        await self.room_manager.join(room, websocket)  # type: ignore[attr-defined]
                    self._online_move(getattr(websocket, "nick", "Bean"), room)
                    # optional announce move
                    try:
                        evt = json.dumps({"type": "system", "event": "moved", "nickname": getattr(websocket, "nick", "Bean")})
                        await self.room_manager.broadcast(room, evt, sender=None, echo_to_sender=True)
                    except Exception:
                        pass
                    continue

                if text.startswith("/showall"):
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
                            await websocket.send_text(
                                json.dumps({"type": "system", "event": "blocked", "nickname": websocket.nick})
                            )
                            self.security_logger.warning(f"DLP blocked message from {websocket.nick}: {incoming_text}")
                            continue
                        _, _, processed_text = processed_message.split("|", 2)
                        message = processed_text
                        self.app_logger.info(f"ALLOWED: {raw_message}")
                        outgoing_text = processed_text
                    except Exception as e:
                        self.app_logger.error(f"Pipeline error: {e}")
                        outgoing_text = incoming_text
                else:
                    self.app_logger.info(f"No pipeline - using original message: {text}")
                    message = text
                    outgoing_text = incoming_text

                payload = json.dumps({"type": "chat", "nickname": websocket.nick, "text": outgoing_text})
                await self.room_manager.broadcast(room, payload, sender=websocket, echo_to_sender=True)

        except WebSocketDisconnect:
            pass
        finally:
            # cleanup on disconnect
            try:
                if hasattr(self.room_manager, "leave"):
                    await self.room_manager.leave(room, websocket)  # type: ignore[attr-defined]
            finally:
                self.clients.discard(websocket)
                self._online_drop(getattr(websocket, "nick", ""))
                try:
                    left_evt = json.dumps({"type": "system", "event": "left", "nickname": getattr(websocket, "nick", "anon")})
                    await self.room_manager.broadcast(room, left_evt, sender=None, echo_to_sender=False)
                except Exception:
                    pass

    def _remember_room(self, room: str) -> None:
        if room:
            KNOWN_ROOMS.add(room)               

# --- FastAPI app + endpoints ---
app = FastAPI(title="TSPO Chat Server")

# CORS (dev-friendly; tighten for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # TODO: restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_server = ChatServer()


# WebSocket endpoint used by the frontend
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    room: Optional[str] = Query(None),
    nick: Optional[str] = Query(None),
    token: Optional[str] = Query(None),  # not validated in this POC
):
    """
    Frontend connects with: /ws?room=<name>&nick=<nick>&token=<token>
    If room is omitted, fallback to settings.default_room (or 'lobby').
    """
    # Pass initial room/nick into the handler (keeps your original logic intact)
    await chat_server.handle_client(websocket, initial_room=room, initial_nick=nick)


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Minimal Auth (POC) ---
def _next_user_id() -> int:
    global _next_uid
    uid = _next_uid
    _next_uid += 1
    return uid


def _make_token(nick: str) -> str:
    # NOTE: replace with real JWT in production
    return f"token-{nick}"


@app.post("/auth/register")
async def register(c: Credentials):
    if len(c.password) < 4:
        raise HTTPException(status_code=400, detail="Password too short")
    if c.nickname in USERS:
        raise HTTPException(status_code=409, detail="Nickname already taken")
    uid = _next_user_id()
    USERS[c.nickname] = {"password": c.password, "user_id": uid}
    return {"user_id": uid, "token": _make_token(c.nickname), "nickname": c.nickname}


@app.post("/auth/login")
async def login(c: Credentials):
    user = USERS.get(c.nickname)
    if not user or user["password"] != c.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"user_id": user["user_id"], "token": _make_token(c.nickname), "nickname": c.nickname}


# --- Rooms REST ---
@app.get("/rooms")
async def list_rooms():
    """
    Returns all known rooms (even empty) with member counts.
    Frontend expects shape: {rooms: {name: count, ...}}
    """
    counts = await chat_server.room_manager.get_room_list()  # active rooms with members
    all_rooms = set(KNOWN_ROOMS) | set(counts.keys())
    return {
        "rooms": {
            name: counts.get(name, 0)
            for name in sorted(all_rooms)
        }
    }



@app.post("/rooms")
async def create_room(r: RoomIn):
    """
    No hard 'create' concept in this RoomManager — rooms are created on first join.
    We keep this endpoint for UX: success is enough. You can persist to DB if needed.
    """
    name = (r.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Room name is required")
    KNOWN_ROOMS.add(name)
    return {"ok": True, "name": name}


# --- Admin endpoint for DLP management (kept from your code) ---
@app.post("/admin/dlp/reload")
async def reload_dlp_rules():
    """Reload DLP rules from configuration file"""
    try:
        if chat_server.pipeline and hasattr(chat_server.pipeline, 'handlers'):
            for handler in chat_server.pipeline.handlers:
                if hasattr(handler, 'dlp_handler'):
                    with open("config/dlp_rules.json") as f:
                        handler.dlp_handler.config = json.load(f)
                    return {"status": "success", "message": "DLP rules reloaded"}
        return {"status": "error", "message": "DLP not initialized"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.websocket("/ws/{room}")
async def websocket_endpoint_room(
    websocket: WebSocket,
    room: str,
    nick: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    # pass initial room/nick to keep your existing logic intact
    await chat_server.handle_client(websocket, initial_room=room, initial_nick=nick)