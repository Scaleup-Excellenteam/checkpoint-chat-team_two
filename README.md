# Chat Application - How to Run

## Prerequisites

1. **Python 3.11+** installed
2. **Required packages** installed:
   ```bash
   pip install fastapi uvicorn websockets aiohttp pydantic-settings
   ```

## Running the Server

### Option 1: Direct Python (Recommended)
```bash
# Navigate to project root
cd checkpoint-chat-team_two

# Set Python path and run server
set PYTHONPATH=%CD%
python -c "import sys; sys.path.append('.'); sys.path.append('server'); import uvicorn; uvicorn.run('server.app:app', host='0.0.0.0', port=8080)"
```

### Option 2: Using uvicorn directly
```bash
cd checkpoint-chat-team_two
set PYTHONPATH=%CD%
python -m uvicorn server.app:app --host 0.0.0.0 --port 8080
```

### Option 3: Docker Compose (Full Stack)
```bash
docker compose up
```

## Running the Client

### Option 1: Python Client (Recommended)
```bash
# Navigate to client directory
cd client

# Install dependencies
pip install websockets asyncio

# Run client (replace IP with server IP)
python interactive_client.py --url ws://SERVER_IP:8080/ws --nick YourName --room lobby
```

### Option 2: Docker Client Only
```bash
# Build client image
docker build -t chat-client ./client

# Run client (replace IP with server IP)
docker run -it --rm -e SERVER_URL=ws://SERVER_IP:8080/ws chat-client
```

## Configuration

### Environment Variables
Copy `.env.example` to `.env` and modify as needed:
```bash
cp .env.example .env
```

Key settings:
- `HOST=0.0.0.0` (for external connections)
- `PORT=8080`
- `DEFAULT_ROOM=lobby`
- `ENABLE_DLP=false` (set to true for content filtering)

## Testing Connection

Use the connection test script:
```bash
python test_connection.py ws://SERVER_IP:8080/ws
```

## Troubleshooting

### Server Issues
1. **Port already in use**: Change port in `.env` file or use different port
2. **Import errors**: Make sure `PYTHONPATH` is set correctly
3. **Permission denied**: Run as administrator or use different port

### Client Connection Issues
1. **Connection refused**: 
   - Check if server is running
   - Verify IP address and port
   - Check Windows Firewall settings
2. **Wrong IP**: Use `ipconfig` to find correct IP address

### Network Setup
1. **Find your IP address**:
   ```bash
   ipconfig
   ```
   Look for "IPv4 Address" under your active network adapter

2. **Allow through Windows Firewall**:
   - Go to Windows Defender Firewall
   - Allow Python through firewall
   - Or temporarily disable firewall for testing

## Example Usage

1. **Start server** on computer A:
   ```bash
   python -c "import sys; sys.path.append('.'); sys.path.append('server'); import uvicorn; uvicorn.run('server.app:app', host='0.0.0.0', port=8080)"
   ```

2. **Connect client** from computer B:
   ```bash
   python interactive_client.py --url ws://COMPUTER_A_IP:8080/ws --nick Alice --room lobby
   ```

3. **Chat commands**:
   - `/nick NewName` - Change nickname
   - `/join RoomName` - Join different room
   - `/showall on/off` - Toggle message visibility
   - Type normally to send messages

## Health Check

Test if server is running:
```bash
curl http://SERVER_IP:8080/health
```

Should return: `{"status":"ok"}`