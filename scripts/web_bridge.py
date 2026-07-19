"""Docker-bridge relay: 172.17.0.1:18000 -> 127.0.0.1:8000 (the hub).

The public front (os.<ip>.sslip.io) is served by the stack-caddy CONTAINER, and
from inside a container 127.0.0.1 is the container itself — host services must be
reachable on the docker bridge IP (the house convention: stt on 8787, tg-pilot on
8788 bind there). The hub deliberately stays on 127.0.0.1 (local trust model,
tunnels, audits unchanged); this relay exposes it to the bridge ONLY, and ufw
keeps that IP unreachable from the internet — the only public door is Caddy,
which fronts this with basic_auth + TLS.

Runs as ramin-web-bridge.service. Stdlib only.
"""
from __future__ import annotations

import asyncio

LISTEN_HOST = "172.17.0.1"
LISTEN_PORT = 18000
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8000


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _handle(cr: asyncio.StreamReader, cw: asyncio.StreamWriter) -> None:
    try:
        ur, uw = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
    except Exception:
        cw.close()
        return
    await asyncio.gather(_pipe(cr, uw), _pipe(ur, cw))


async def main() -> None:
    server = await asyncio.start_server(_handle, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
