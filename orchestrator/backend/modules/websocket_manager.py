#!/usr/bin/env python3
"""
WebSocket Manager Module
Handles WebSocket connections and event broadcasting for real-time updates.

Enhanced with:
- Connection state tracking (connecting, connected, disconnected, error)
- Heartbeat/ping-pong to keep connections alive and detect stale connections
- Per-connection metadata including missed ping counts and pong events
"""

from typing import List, Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
from datetime import datetime
from .logger import get_logger

logger = get_logger()


class ConnectionState:
    """WebSocket connection state constants."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts events to all connected clients.

    Enhanced features:
    - Heartbeat/ping-pong mechanism (30s interval, 10s timeout)
    - Stale connection detection (closes after 3 missed pings)
    - Connection state tracking per client
    - Graceful disconnection cleanup
    """

    HEARTBEAT_INTERVAL = 30  # seconds between pings
    HEARTBEAT_TIMEOUT = 10   # seconds to wait for pong
    MAX_MISSED_PINGS = 3     # close connection after this many missed pings

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
        # Per-connection heartbeat tasks
        self._heartbeat_tasks: Dict[WebSocket, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, client_id: str = None):
        """
        Accept a new WebSocket connection and register it.
        Starts the heartbeat loop for the connection.
        """
        await websocket.accept()
        self.active_connections.append(websocket)

        # Store metadata including heartbeat tracking
        client_id = client_id or f"client_{len(self.active_connections)}"
        pong_event = asyncio.Event()
        self.connection_metadata[websocket] = {
            "client_id": client_id,
            "connected_at": datetime.now().isoformat(),
            "state": ConnectionState.CONNECTED,
            "missed_pings": 0,
            "pong_event": pong_event,
            "last_activity": datetime.now().isoformat(),
        }

        logger.success(
            f"WebSocket client connected: {client_id} | "
            f"Total connections: {len(self.active_connections)}"
        )

        # Send welcome message
        await self.send_to_client(
            websocket,
            {
                "type": "connection_established",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat(),
                "message": "Connected to Orchestrator Backend",
            },
        )

        # Start heartbeat loop for this connection
        task = asyncio.create_task(
            self._heartbeat_loop(websocket, client_id),
            name=f"heartbeat-{client_id}",
        )
        self._heartbeat_tasks[websocket] = task

    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection from the active list.
        Cancels the heartbeat task and updates connection state.
        """
        if websocket in self.active_connections:
            metadata = self.connection_metadata.get(websocket, {})
            client_id = metadata.get("client_id", "unknown")

            self.active_connections.remove(websocket)
            if websocket in self.connection_metadata:
                self.connection_metadata[websocket]["state"] = ConnectionState.DISCONNECTED
                del self.connection_metadata[websocket]

            # Cancel heartbeat task
            task = self._heartbeat_tasks.pop(websocket, None)
            if task and not task.done():
                task.cancel()

            logger.warning(
                f"WebSocket client disconnected: {client_id} | "
                f"Total connections: {len(self.active_connections)}"
            )

    async def handle_pong(self, websocket: WebSocket):
        """
        Handle a pong response from the client.
        Resets the missed ping counter and signals the pong event.
        """
        metadata = self.connection_metadata.get(websocket)
        if metadata:
            metadata["missed_pings"] = 0
            metadata["last_activity"] = datetime.now().isoformat()
            pong_event: asyncio.Event = metadata.get("pong_event")
            if pong_event:
                pong_event.set()
            client_id = metadata.get("client_id", "unknown")
            logger.debug(f"Pong received from {client_id}")

    async def send_to_client(self, websocket: WebSocket, data: dict):
        """
        Send JSON data to a specific client.
        """
        try:
            await websocket.send_json(data)
            logger.debug(f"📤 Sent to client: {data.get('type', 'unknown')}")
            # Update last activity timestamp
            metadata = self.connection_metadata.get(websocket)
            if metadata:
                metadata["last_activity"] = datetime.now().isoformat()
        except Exception as e:
            logger.error(f"Failed to send to client: {e}")
            self.disconnect(websocket)

    async def broadcast(self, data: dict, exclude: WebSocket = None):
        """
        Broadcast JSON data to all connected clients (except optionally one).
        """
        if not self.active_connections:
            logger.debug(f"No active connections, skipping broadcast: {data.get('type')}")
            return

        event_type = data.get("type", "unknown")
        logger.websocket_event(event_type, {k: v for k, v in data.items() if k != "type"})

        # Add timestamp if not present
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()

        disconnected = []

        for connection in self.active_connections:
            if connection == exclude:
                continue

            try:
                await connection.send_json(data)
                # Update last activity
                metadata = self.connection_metadata.get(connection)
                if metadata:
                    metadata["last_activity"] = datetime.now().isoformat()
            except Exception as e:
                logger.error(f"Failed to broadcast to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws)

        logger.debug(
            f"📡 Broadcast complete: {event_type} → {len(self.active_connections) - len(disconnected)} clients"
        )

    async def _heartbeat_loop(self, websocket: WebSocket, client_id: str):
        """
        Background heartbeat loop for a specific connection.

        Sends a ping every HEARTBEAT_INTERVAL seconds.
        Waits HEARTBEAT_TIMEOUT seconds for a pong response.
        Closes the connection after MAX_MISSED_PINGS consecutive missed pongs.
        """
        try:
            while websocket in self.active_connections:
                # Wait for the heartbeat interval
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

                # Check if connection is still active after sleep
                if websocket not in self.active_connections:
                    break

                metadata = self.connection_metadata.get(websocket)
                if not metadata:
                    break

                # Prepare pong event — clear before sending ping
                pong_event: asyncio.Event = metadata.get("pong_event")
                if pong_event:
                    pong_event.clear()

                # Send ping
                logger.debug(f"Sending ping to {client_id}")
                try:
                    await websocket.send_json({
                        "type": "ping",
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception as e:
                    logger.error(f"Failed to send ping to {client_id}: {e}")
                    self.disconnect(websocket)
                    break

                # Wait for pong within timeout
                try:
                    await asyncio.wait_for(
                        asyncio.shield(pong_event.wait()),
                        timeout=self.HEARTBEAT_TIMEOUT,
                    )
                    # Pong received — missed_pings already reset in handle_pong()
                    logger.debug(f"Heartbeat OK for {client_id}")

                except asyncio.TimeoutError:
                    # No pong received within timeout
                    metadata = self.connection_metadata.get(websocket)
                    if not metadata:
                        break

                    metadata["missed_pings"] = metadata.get("missed_pings", 0) + 1
                    missed = metadata["missed_pings"]

                    logger.warning(
                        f"Missed pong from {client_id}: "
                        f"{missed}/{self.MAX_MISSED_PINGS}"
                    )

                    if missed >= self.MAX_MISSED_PINGS:
                        logger.error(
                            f"Closing stale connection {client_id} after "
                            f"{missed} missed pings"
                        )
                        self.disconnect(websocket)
                        break

        except asyncio.CancelledError:
            # Task was cancelled (normal during disconnect)
            logger.debug(f"Heartbeat task cancelled for {client_id}")
        except Exception as e:
            logger.error(f"Heartbeat loop error for {client_id}: {e}")

    # ========================================================================
    # Connection State API
    # ========================================================================

    def get_connection_state(self, websocket: WebSocket) -> str:
        """Get the current state of a specific connection."""
        metadata = self.connection_metadata.get(websocket)
        if metadata:
            return metadata.get("state", ConnectionState.DISCONNECTED)
        return ConnectionState.DISCONNECTED

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)

    def get_all_client_ids(self) -> List[str]:
        """Get list of all connected client IDs."""
        return [
            metadata.get("client_id", "unknown")
            for metadata in self.connection_metadata.values()
        ]

    def get_connection_info(self) -> List[Dict[str, Any]]:
        """Get connection info for all active connections (for monitoring)."""
        info = []
        for ws, metadata in self.connection_metadata.items():
            info.append({
                "client_id": metadata.get("client_id"),
                "connected_at": metadata.get("connected_at"),
                "state": metadata.get("state"),
                "missed_pings": metadata.get("missed_pings", 0),
                "last_activity": metadata.get("last_activity"),
            })
        return info

    # ========================================================================
    # Event Broadcasting Methods
    # ========================================================================

    async def broadcast_agent_created(self, agent_data: dict):
        """Broadcast agent creation event"""
        await self.broadcast({"type": "agent_created", "agent": agent_data})

    async def broadcast_agent_updated(self, agent_id: str, agent_data: dict):
        """Broadcast agent update event"""
        await self.broadcast(
            {"type": "agent_updated", "agent_id": agent_id, "agent": agent_data}
        )

    async def broadcast_agent_deleted(self, agent_id: str):
        """Broadcast agent deletion event"""
        await self.broadcast({"type": "agent_deleted", "agent_id": agent_id})

    async def broadcast_agent_status_change(
        self, agent_id: str, old_status: str, new_status: str
    ):
        """Broadcast agent status change"""
        await self.broadcast(
            {
                "type": "agent_status_changed",
                "agent_id": agent_id,
                "old_status": old_status,
                "new_status": new_status,
            }
        )

    async def broadcast_agent_log(self, log_data: dict):
        """Broadcast agent log entry"""
        await self.broadcast({"type": "agent_log", "log": log_data})

    async def broadcast_agent_summary_update(self, agent_id: str, summary: str):
        """Broadcast agent summary update (latest log summary for an agent)"""
        await self.broadcast({
            "type": "agent_summary_update",
            "agent_id": agent_id,
            "summary": summary
        })

    async def broadcast_orchestrator_updated(self, orchestrator_data: dict):
        """Broadcast orchestrator update (cost, tokens, status, etc.)"""
        await self.broadcast({
            "type": "orchestrator_updated",
            "orchestrator": orchestrator_data
        })

    async def broadcast_system_log(self, log_data: dict):
        """Broadcast system log entry"""
        await self.broadcast({"type": "system_log", "log": log_data})

    async def broadcast_chat_message(self, message_data: dict):
        """Broadcast chat message"""
        await self.broadcast({"type": "chat_message", "message": message_data})

    async def broadcast_error(self, error_message: str, details: dict = None):
        """Broadcast error event"""
        await self.broadcast(
            {
                "type": "error",
                "message": error_message,
                "details": details or {},
            }
        )

    async def broadcast_chat_stream(
        self, orchestrator_agent_id: str, chunk: str, is_complete: bool = False
    ):
        """
        Broadcast chat response chunk for real-time streaming.

        Args:
            orchestrator_agent_id: UUID of orchestrator agent
            chunk: Text chunk to stream
            is_complete: True if this is the final chunk
        """
        await self.broadcast(
            {
                "type": "chat_stream",
                "orchestrator_agent_id": orchestrator_agent_id,
                "chunk": chunk,
                "is_complete": is_complete,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def set_typing_indicator(
        self, orchestrator_agent_id: str, is_typing: bool
    ):
        """
        Broadcast typing indicator state.

        Args:
            orchestrator_agent_id: UUID of orchestrator agent
            is_typing: True if orchestrator is typing, False if stopped
        """
        await self.broadcast(
            {
                "type": "chat_typing",
                "orchestrator_agent_id": orchestrator_agent_id,
                "is_typing": is_typing,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def send_heartbeat(self):
        """Send heartbeat to all connected clients (legacy method for compatibility)."""
        await self.broadcast(
            {
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat(),
                "active_connections": self.get_connection_count(),
            }
        )


# Global WebSocket manager instance
ws_manager = WebSocketManager()


def get_websocket_manager() -> WebSocketManager:
    """Get the global WebSocket manager instance"""
    return ws_manager
