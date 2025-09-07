# checkpoint-chat-team_two

Overview

To connect the Dockerized chat client to an external server (e.g., 172.20.10.11:8090), we use a local proxy (netsh portproxy).

The proxy forwards requests from 127.0.0.1:8099 to the real server.
Inside Docker, the client connects to host.docker.internal:8099.

Steps
1. Create a proxy

Run the proxy_simple.ps1 script (from PowerShell):

.\proxy_simple.ps1 -TargetAddress 172.20.10.11 -TargetPort 8090 -ListenPort 8099 -Action add


TargetAddress = server IP.
TargetPort = server port.
ListenPort = local port (default: 8099).

2. Verify the proxy
curl http://127.0.0.1:8099/health

If the server is up, you’ll see JSON like:
{"status":"ok","total_clients":1,"rooms":["lobby"]}

3. Run the client in Docker

From the project folder (where docker-compose.yml exists):

docker compose run --rm --no-deps `
  -e SERVER_URL=ws://host.docker.internal:8099/ws `
  -e NAME=Lior `
  client


SERVER_URL points to the proxy (host.docker.internal:8099).
NAME is the nickname in the chat (change as needed).
--rm removes the container after exit.
--no-deps ensures only the client runs (not the whole stack).

4. Remove the proxy when done

Clean up the proxy rule with:
.\proxy_simple.ps1 -ListenPort 8099 -Action remove


Workflow Summary:
1). Add proxy → create forwarding to the remote server.
2). Check proxy → test with curl.
3). Run client → connect via Docker using host.docker.internal.
4).Remove proxy → clean up when finished.