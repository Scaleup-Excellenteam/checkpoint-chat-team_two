# server/app.py
from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from room_manager import RoomManager  # must exist
from logging_config import setup_logging

# --- Optional pipeline (keep tests green if missing) ---
try:
    from message_pipline import MessagePipeline, ValidationHandler, SecurityHandler  # noqa: F401
except Exception:
    MessagePipeline = None  # type: ignore

# --- Optional schemas/auth (for real login/register); falls back to anon if missing ---
try:
    from schemas import (
        RegisterIn, RegisterOut, LoginIn, LoginOut,
        CreateRoomIn, RoomListOut, RoomInfoOut,
    )
    HAVE_SCHEMAS = True
except Exception:
    HAVE_SCHEMAS = False

try:
    from auth_store import create_user, login_user, get_user_by_token  # POC in-memory auth
    HAVE_AUTH = True
except Exception:
    HAVE_AUTH = False

# Try to import User dataclass from RoomManager module (newer design)
try:
    from room_manager import User  # type: ignore
    HAVE_USER = True
except Exception:
    HAVE_USER = False


class ChatServer:
    """
    Chat server wrapper that:
      - manages join/leave via RoomManager
      - supports commands (/nick, /join, /showall) without echo
      - broadcasts chat payloads
      - optionally integrates auth tokens and per-room join
    """

    def __init__(self) -> None:
        # loggers
        self.app_logger, self.security_logger = setup_logging()

        # optional pipeline (keep flexible)
        self.pipeline: Optional[MessagePipeline] = None  # type: ignore[assignment]
        try:
            if MessagePipeline is not None:
                self.pipeline = MessagePipeline([])  # plug real handlers later
        except Exception:
            self.pipeline = None

        # room manager (pass pipeline if ctor supports it)
        try:
            self.room_manager = RoomManager(self.pipeline)  # type: ignore[arg-type]
        except TypeError:
            self.room_manager = RoomManager()

        self.clients = set()

    async def _ensure_room_safe(self, room: str) -> None:
        """Ensure the room exists if manager supports ensure_room()."""
        if hasattr(self.room_manager, "ensure_room"):
            try:
                await self.room_manager.ensure_room(room)  # type: ignore[attr-defined]
            except TypeError:
                # some implementations may be sync
                self.room_manager.ensure_room(room)  # type: ignore[attr-defined]

    async def _join_safe(self, room: str, ws: WebSocket, nickname: str, user_id: str | None = None) -> None:
        """
        Join room with best-effort compatibility:
        - New API: join(room, ws, user=User(...)) + register_user()
        - Old API: join(room, ws)
        """
        # Set nick for UI lists even on legacy managers
        setattr(ws, "nick", nickname)
        setattr(ws, "showall", False)

        # New-style RoomManager with users
        if HAVE_USER and hasattr(self.room_manager, "register_user"):
            user_obj = User(user_id=user_id or "anon", nickname=nickname)  # type: ignore
            try:
                await self.room_manager.register_user(user_obj)  # type: ignore[attr-defined]
            except TypeError:
                self.room_manager.register_user(user_obj)  # type: ignore[attr-defined]

            if hasattr(self.room_manager, "join"):
                try:
                    await self.room_manager.join(room, ws, user=user_obj)  # type: ignore[attr-defined]
                    return
                except TypeError:
                    # Signature mismatch -> fall back below
                    pass

        # Legacy fallback: join(room, ws)
        if hasattr(self.room_manager, "join"):
            try:
                await self.room_manager.join(room, ws)  # type: ignore[attr-defined]
            except TypeError:
                self.room_manager.join(room, ws)  # type: ignore[attr-defined]

    async def _leave_safe(self, room: str, ws: WebSocket) -> None:
        """Leave room with compatibility for legacy/new managers."""
        if hasattr(self.room_manager, "leave"):
            try:
                await self.room_manager.leave(room, ws)  # type: ignore[attr-defined]
            except TypeError:
                self.room_manager.leave(room, ws)  # type: ignore[attr-defined]

    async def _broadcast_safe(self, room: str, message: str, sender: Optional[WebSocket] = None, echo_to_sender: bool = True) -> None:
        """Broadcast wrapper; cleans up dead sockets inside manager."""
        await self.room_manager.broadcast(
            room,
            message,
            sender=sender,  # may be None
            echo_to_sender=echo_to_sender,
        )

    async def handle_client(
        self,
        websocket: WebSocket,
        *,
        initial_room: str,
        nickname: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Accept client, join room, process commands, broadcast chat."""
        await websocket.accept()

        room = initial_room or settings.default_room

        # Ensure room exists (if supported)
        await self._ensure_room_safe(room)

        # Join (new API if available, fallback to old)
        await self._join_safe(room, websocket, nickname=nickname, user_id=user_id)

        # Announce JOIN (do not echo to sender)
        try:
            await self._broadcast_safe(
                room,
                json.dumps({"type": "system", "event": "join", "nickname": nickname}),
                echo_to_sender=False,
            )
        except Exception:
            pass

        self.clients.add(websocket)

        try:
            while True:
                raw_text = await websocket.receive_text()

                # Optional: parse JSON envelopes sent by client
                # - ignore {type:"ping"}
                # - if {type:"chat", text} -> extract text
                msg_text = raw_text
                try:
                    data = json.loads(raw_text)
                    if isinstance(data, dict):
                        if data.get("type") == "ping":
                            continue  # skip heartbeats
                        if data.get("type") == "chat":
                            msg_text = data.get("text", "")
                except Exception:
                    # not JSON, keep as-is
                    pass

                # ---- Commands (no echo) ----
                if raw_text.startswith("/nick "):
                    new_nick = raw_text.split(" ", 1)[1].strip() or "anon"
                    websocket.nick = new_nick
                    nickname = new_nick
                    continue

                if raw_text.startswith("/join "):
                    new_room = raw_text.split(" ", 1)[1].strip() or settings.default_room
                    # leave old
                    await self._leave_safe(room, websocket)
                    # announce LEAVE in old room
                    try:
                        await self._broadcast_safe(
                            room,
                            json.dumps({"type": "system", "event": "leave", "nickname": nickname}),
                            echo_to_sender=False,
                        )
                    except Exception:
                        pass
                    # ensure + join new
                    await self._ensure_room_safe(new_room)
                    await self._join_safe(new_room, websocket, nickname=nickname, user_id=user_id)
                    room = new_room
                    # announce JOIN in new room
                    try:
                        await self._broadcast_safe(
                            room,
                            json.dumps({"type": "system", "event": "join", "nickname": nickname}),
                            echo_to_sender=False,
                        )
                    except Exception:
                        pass
                    continue

                if raw_text.startswith("/showall"):
                    parts = raw_text.split()
                    if len(parts) == 2 and parts[1].lower() in {"on", "off"}:
                        websocket.showall = (parts[1].lower() == "on")
                    continue

                # ---- Real chat payload (send JSON envelope) ----
                message = msg_text
                await self._broadcast_safe(
                    room,
                    json.dumps({
                        "type": "chat",
                        "room": room,
                        "nickname": nickname,
                        "text": message,
                    }),
                    sender=websocket,
                    echo_to_sender=True,  # sender also receives their own message
                )

        except WebSocketDisconnect:
            pass
        finally:
            await self._leave_safe(room, websocket)
            self.clients.discard(websocket)
            # Announce LEAVE (only to others)
            try:
                await self._broadcast_safe(
                    room,
                    json.dumps({"type": "system", "event": "leave", "nickname": nickname}),
                    echo_to_sender=False
                )
            except Exception:
                pass


# -------------------- FastAPI app --------------------
app = FastAPI(title="TSPO Chat Server")

# CORS for simple static frontends (file:// or http://localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         # POC/dev only; restrict in prod
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_server = ChatServer()


# ---------- Health ----------
@app.get("/health")
async def health():
    # Keep response minimal for tests
    return {"status": "ok"}


# ---------- Auth (optional) ----------
if HAVE_AUTH and HAVE_SCHEMAS:
    @app.post("/auth/register", response_model=RegisterOut)
    async def register(payload: RegisterIn):
        try:
            uid, tok = create_user(payload.nickname, payload.password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        # If manager supports users, register in memory as well
        if HAVE_USER and hasattr(chat_server.room_manager, "register_user"):
            try:
                from room_manager import User  # local import to avoid circular
                user_obj = User(user_id=uid, nickname=payload.nickname)  # type: ignore
                await chat_server.room_manager.register_user(user_obj)  # type: ignore
            except Exception:
                pass
        return RegisterOut(user_id=uid, token=tok, nickname=payload.nickname)

    @app.post("/auth/login", response_model=LoginOut)
    async def login(payload: LoginIn):
        try:
            uid, tok = login_user(payload.nickname, payload.password)
        except ValueError:
            raise HTTPException(status_code=401, detail="invalid credentials")
        if HAVE_USER and hasattr(chat_server.room_manager, "register_user"):
            try:
                from room_manager import User
                user_obj = User(user_id=uid, nickname=payload.nickname)  # type: ignore
                await chat_server.room_manager.register_user(user_obj)  # type: ignore
            except Exception:
                pass
        return LoginOut(user_id=uid, token=tok, nickname=payload.nickname)

    @app.get("/me")
    async def me(token: str = Query(...)):
        info = get_user_by_token(token)
        if not info:
            raise HTTPException(status_code=401, detail="invalid token")
        uid, nick = info
        return {"user_id": uid, "nickname": nick}


# ---------- Rooms (optional) ----------
if HAVE_SCHEMAS:
    @app.get("/rooms", response_model=RoomListOut)
    async def list_rooms():
        rooms = await chat_server.room_manager.get_room_list()
        return RoomListOut(rooms=rooms)

    @app.post("/rooms", response_model=RoomInfoOut, status_code=201)
    async def create_room(payload: CreateRoomIn):
        # If manager supports ensure_room, use it; otherwise, joining later will create it
        if hasattr(chat_server.room_manager, "ensure_room"):
            await chat_server.room_manager.ensure_room(payload.name)  # type: ignore
        info = await chat_server.room_manager.get_room_info(payload.name)
        return RoomInfoOut(**info)


# ---------- WebSocket ----------
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    room: Optional[str] = Query(None, description="Room name. Defaults to settings.default_room."),
    token: Optional[str] = Query(None, description="Auth token; if missing -> anon user"),
):
    """
    Supports two modes:
    1) Auth mode: pass ?room=<name>&token=<token> (if auth_store/schemas are present)
    2) Anonymous mode: omit token; default nickname 'anon'
    """
    # Resolve nickname/user_id from token if available
    nickname = "anon"
    user_id: Optional[str] = None

    if HAVE_AUTH and token:
        info = get_user_by_token(token)
        if not info:
            # Soft-fail: close politely
            await websocket.accept()
            await websocket.send_text(json.dumps({"type": "error", "message": "invalid token"}))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_id, nickname = info[0], info[1]

    initial_room = room or settings.default_room

    # Hand over to ChatServer logic
    await chat_server.handle_client(
        websocket,
        initial_room=initial_room,
        nickname=nickname,
        user_id=user_id,
    )
