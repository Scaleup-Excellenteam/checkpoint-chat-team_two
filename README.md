# Dockerized FastAPI WebSocket Chat 

Dockerized FastAPI WebSocket chat; migrated to Pydantic v2 via pydantic-settings, fixed imports, unified port 8080, full server copied to image, healthcheck + tests.

-----

## Prerequisites

  * **Docker:** Ensure Docker is installed and running on your system.
  * **Python 3.8+ & Poetry:** Required for the local Python client and for running tests.
  * **Windows PowerShell:** Required for the proxy setup if you need to connect to an external server.

-----

## Quick Start (Local Server)

1.  **Build and run the server:**

    ```bash
    docker compose build --no-cache
    docker compose up -d server
    ```

2.  **Verify server health:**

    ```bash
    curl http://localhost:8080/health
    # Expected output: {"status":"healthy"}
    ```

3.  **Connect clients:**

      * **Docker Client:**
        ```bash
        docker compose run --rm client
        ```
      * **Local Python Client:**
        ```bash
        poetry install
        poetry run python client/client.py
        ```

    Messages sent from either client will appear in both terminals.

-----

## Connecting to an External Server (via Proxy)

To connect the Dockerized client to a server running on a different machine (e.g., `172.20.10.11:8090`), a local proxy is used to forward requests.

1.  **Create a local proxy:**
    Run the `proxy_simple.ps1` script from PowerShell, replacing `TargetAddress` and `TargetPort` with your server's details. `ListenPort` is the local port the proxy will use.

    ```powershell
    .\proxy_simple.ps1 -TargetAddress 172.20.10.13 -TargetPort 8080 -ListenPort 8099 -Action add
    ```

2.  **Verify the proxy connection:**

    ```bash
    curl http://127.0.0.1:8099/health
    # A successful response from the remote server will look like:
    # {"status":"ok","total_clients":1,"rooms":["lobby"]}
    ```

3.  **Run the client via the proxy:**
    Connect the Docker client to the local proxy using `host.docker.internal`.

    ```bash
    docker compose run --rm --no-deps `
      -e SERVER_URL=ws://host.docker.internal:8099/ws `
      -e NAME=Lior `
      client
    ```

4.  **Remove the proxy:**
    When finished, clean up the proxy rule with the following command:

    ```powershell
    .\proxy_simple.ps1 -ListenPort 8099 -Action remove
    ```

-----

## Running Tests

To run the project tests, ensure you have a `pytest.ini` file that sets the Python path correctly.

```bash
pytest -q
```

