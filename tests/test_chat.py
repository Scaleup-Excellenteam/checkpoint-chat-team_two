# tests/test_chat.py
from starlette.testclient import TestClient
from app import app 

def test_two_clients_see_each_other():
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws1, client.websocket_connect("/ws") as ws2:
        # Optional: set nicks/rooms if your server requires it
        ws1.send_text("/nick alice")
        ws2.send_text("/nick bob")
        # NOTE: do NOT pre-drain here; it can block if the server hasn't echoed yet.

        # Send the actual chat message
        ws1.send_text("hello from alice")

        # The sender should receive its own message (or a formatted variant)
        got_sender = False
        for _ in range(5):
            t1 = ws1.receive_text()
            if "hello from alice" in t1:
                got_sender = True
                break

        # The other client should see it too
        got_peer = False
        for _ in range(5):
            t2 = ws2.receive_text()
            if "hello from alice" in t2:
                got_peer = True
                break

        assert got_sender, "sender did not receive its own chat message"
        assert got_peer, "peer did not receive the sender's chat message"
