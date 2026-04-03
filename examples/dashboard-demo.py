"""Dashboard monitoring demo — see docs/dashboard-monitoring.md for full reference."""

import requests
import asyncio
import websockets

BASE_URL = "http://localhost:8080"


def query_agent_status():
    """Query the agent status endpoint."""
    resp = requests.get(f"{BASE_URL}/api/agents/status")
    resp.raise_for_status()
    print("Agent status:")
    print(resp.json())


def query_cost_summary():
    """Query the cost summary endpoint."""
    resp = requests.get(f"{BASE_URL}/api/cost/summary")
    resp.raise_for_status()
    print("Cost summary:")
    print(resp.json())


async def listen_websocket():
    """Connect to the WebSocket and print the first event."""
    async with websockets.connect(f"ws://localhost:8080/ws") as ws:
        msg = await ws.recv()
        print("WebSocket event:")
        print(msg)


if __name__ == "__main__":
    query_agent_status()
    query_cost_summary()
    asyncio.run(listen_websocket())
