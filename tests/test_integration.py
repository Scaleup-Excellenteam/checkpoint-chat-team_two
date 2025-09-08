import pytest
from fastapi.testclient import TestClient
from server.app import app
from server.message_pipline import MessagePipeline, ValidationHandler

# Responsible for integration tests covering message pipeline and concurrent clients

@pytest.fixture
async def server():
    # Start test server
    client = TestClient(app)
    yield client

@pytest.mark.asyncio
async def test_message_pipeline():
    """Test message goes through pipeline"""    
    pipeline = MessagePipeline()
    pipeline.handlers = [ValidationHandler()]
    
    # Valid message
    result = await pipeline.process("lobby|alice|hello", None)
    assert result is not None
    
    # Invalid message (too long)
    long_msg = "lobby|alice|" + "x" * 2000
    result = await pipeline.process(long_msg, None)
    assert result is None

@pytest.mark.asyncio
async def test_concurrent_clients():
    """Test multiple clients can connect"""
    # Implement concurrent client test
    pass