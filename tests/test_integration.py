import os
import time
import pytest
from contextlib import ExitStack
from fastapi.testclient import TestClient

# App & pipeline
from app import app
from message_pipline import MessagePipeline, ValidationHandler

# Configurable delay (seconds) between messages in the sequential 20-clients test
MESSAGE_DELAY_SECONDS = float(os.getenv("E2E_MSG_DELAY", "0.5"))


# ---------------------------
# Helpers
# ---------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Single FastAPI TestClient for this module.
    """
    return TestClient(app)


def ws(client: TestClient, ip: str | None = None):
    """
    Open a WebSocket to /ws. If ip is given, we set X-Forwarded-For to simulate
    different remote hosts (since TestClient runs in-process).
    """
    headers = {}
    if ip:
        headers["X-Forwarded-For"] = ip
    return client.websocket_connect("/ws", headers=headers)


def join_room(sock, room: str, nick: str):
    """
    Set a nickname and join a room using simple command messages.
    If your server ignores these commands, they will become normal chat messages,
    which is fine for these tests (we rely on recv buffering attempts).
    """
    sock.send_text(f"/nick {nick}")
    sock.send_text(f"/join {room}")
    # Do not read ack frames here to avoid blocking; recv_contains has headroom.


def recv_contains(ws, needle: str, attempts: int = 10):
    """
    Read up to `attempts` messages and return the first that contains `needle`.
    Bumped attempts to handle join/welcome/broadcast interleaving under load.
    """
    for _ in range(attempts):
        msg = ws.receive_text()
        if needle in msg:
            return msg
    raise AssertionError(f"Did not receive a message containing '{needle}'")


def wait_between_msgs():
    """
    Sleep for the configured delay between messages in the 20-clients chat test.
    """
    time.sleep(MESSAGE_DELAY_SECONDS)


# ---------------------------
# 0) Pipeline sanity (as before)
# ---------------------------

@pytest.mark.asyncio
async def test_message_pipeline_accepts_and_rejects():
    """
    Goal: keep a fast sanity test on the message pipeline:
      - valid format passes
      - too-long message gets rejected
    """
    pipeline = MessagePipeline()
    pipeline.handlers = [ValidationHandler()]

    # Valid
    result = await pipeline.process("lobby|alice|hello", None)
    assert result is not None

    # Too long
    long_msg = "lobby|alice|" + "x" * 2000
    result = await pipeline.process(long_msg, None)
    assert result is None


# ---------------------------
# 1) Two clients from different IPs
# ---------------------------

def test_two_clients_different_ips_can_talk(client: TestClient):
    """
    Goal #1:
      - Open 2 WS connections with different simulated IPs
      - Have A send to room 'lobby'
      - Ensure B receives the chat payload
    """
    with ws(client, ip="10.0.0.1") as a, ws(client, ip="10.0.0.2") as b:
        a.send_text("lobby|alice|hello-two-clients")

        got = recv_contains(b, "hello-two-clients")
        assert "hello-two-clients" in got


# ---------------------------
# 2) 20 clients in one room (single broadcast)
# ---------------------------

def test_twenty_clients_broadcast_in_one_room(client: TestClient):
    """
    Goal #2 (original):
      - Connect 20 clients to the same room ('stress')
      - First client sends a message
      - All others receive it
    """
    payload = "stress|user0|hello-20"
    with ExitStack() as stack:
        conns = [stack.enter_context(ws(client)) for _ in range(20)]

        # Sender is index 0, others are receivers
        conns[0].send_text(payload)

        # Everyone except sender should get it at least once
        for i, w in enumerate(conns[1:], start=1):
            got = recv_contains(w, "hello-20")
            assert "hello-20" in got, f"Client {i} did not receive broadcast"


# ---------------------------
# 2b) 20 clients sequential chat with delay between messages
# ---------------------------
def test_twenty_clients_sequential_chat_with_delay(client: TestClient):
    """
    20 clients in 'stress', each sends once, wait between messages.
    We assert delivery on a designated receiver to avoid backlog explosions.
    """
    room = "stress"
    with ExitStack() as stack:
        conns = [stack.enter_context(ws(client)) for _ in range(20)]

        # Explicitly join everyone to the room with unique nicks (reduces routing ambiguity)
        for i, c in enumerate(conns):
            join_room(c, room, f"user{i}")

        # Pick a designated receiver (index 1). If sender==1, use index 2 instead.
        designated_receiver = 1

        for i in range(20):
            nick = f"user{i}"
            text = f"hello-from-{nick}"
            payload = f"{room}|{nick}|{text}"
            conns[i].send_text(payload)

            receiver_idx = designated_receiver if i != designated_receiver else (designated_receiver + 1) % 20

            # Larger window to tolerate ack/noise frames already in the queue
            got = recv_contains(conns[receiver_idx], text, attempts=200)
            assert text in got, f"Receiver {receiver_idx} did not get '{text}'"

            # Wait between messages (controlled by MESSAGE_DELAY_SECONDS / E2E_MSG_DELAY)
            wait_between_msgs()

# ---------------------------
# 3) 3–5 active rooms with different clients
# ---------------------------

@pytest.mark.parametrize("rooms", [
    ["lobby", "ops", "kitchen"],                 # 3 rooms
    ["lobby", "ops", "kitchen", "science", "dev"]  # 5 rooms
])
def test_multiple_active_rooms_isolated_broadcast(client: TestClient, rooms: list[str]):
    """
    Goal #3:
      - Spin up N rooms (3 or 5)
      - Put 2 clients in each room
      - Send one message per room
      - Assert clients in that room receive their room's message
      (We assert on the receiver only to avoid echo-to-sender assumptions.)
    """
    with ExitStack() as stack:
        # For simplicity: 2 clients per room
        room_conns: dict[str, list] = {
            r: [stack.enter_context(ws(client)), stack.enter_context(ws(client))]
            for r in rooms
        }

        # Join each pair to its room with unique nicks
        for idx, r in enumerate(rooms):
            a, b = room_conns[r]
            join_room(a, r, f"{r}_a")
            join_room(b, r, f"{r}_b")

        # Send a unique payload per room from the first client in that room
        for r in rooms:
            sender = room_conns[r][0]
            msg = f"{r}|sender|room-msg-{r}"
            sender.send_text(msg)

        # Each room's *receiver* (second client) should catch its room's message
        for r in rooms:
            receiver = room_conns[r][1]
            expected = f"room-msg-{r}"
            got = recv_contains(receiver, expected)
            assert expected in got, f"Room '{r}' receiver missed '{expected}'"


# ---------------------------
# 4) Keep it simple: that’s it for now
# ---------------------------

# These tests cover:
#   (1) Two clients w/ different IPs can communicate
#   (2) Broadcast to 20 clients in a single room
#   (2b) 20 clients talk sequentially with delay between messages
#   (3) Multiple active rooms with different clients (positive isolation)
#
# To speed up the slow test locally/CI:
#   E2E_MSG_DELAY=0.5 pytest -q
