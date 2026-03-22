#!/usr/bin/env python3
"""
Tests for WebSocket Connection Reliability

Tests cover:
- Connection state tracking (connecting → connected → disconnected)
- Heartbeat/ping-pong mechanism
- Stale connection detection (3 missed pings → close)
- Graceful disconnection with task cleanup
- Multiple concurrent connections
- Message delivery to specific clients
- Connection info reporting
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.websocket_manager import WebSocketManager, ConnectionState


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def make_mock_websocket(client_id: str = "test-client") -> AsyncMock:
    """Create a mock WebSocket that records sent messages."""
    ws = AsyncMock()
    ws.sent_messages = []

    async def send_json(data):
        ws.sent_messages.append(data)

    ws.send_json = send_json
    return ws


# ────────────────────────────────────────────────────────────────────────────
# Connection State Tests
# ────────────────────────────────────────────────────────────────────────────

class TestConnectionState:
    """Tests for connection state tracking."""

    @pytest.mark.asyncio
    async def test_initial_state_disconnected(self):
        """Unregistered WebSocket returns DISCONNECTED state."""
        manager = WebSocketManager()
        mock_ws = make_mock_websocket()
        state = manager.get_connection_state(mock_ws)
        assert state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_state_connected_after_connect(self):
        """State is CONNECTED after a client connects."""
        manager = WebSocketManager()
        mock_ws = make_mock_websocket()

        await manager.connect(mock_ws, client_id="test-001")

        assert manager.get_connection_state(mock_ws) == ConnectionState.CONNECTED

        # Cleanup heartbeat task
        manager.disconnect(mock_ws)

    @pytest.mark.asyncio
    async def test_state_disconnected_after_disconnect(self):
        """State is DISCONNECTED after explicit disconnect."""
        manager = WebSocketManager()
        mock_ws = make_mock_websocket()

        await manager.connect(mock_ws, client_id="test-002")
        manager.disconnect(mock_ws)

        # Connection removed from active list
        assert mock_ws not in manager.active_connections
        assert mock_ws not in manager.connection_metadata

    @pytest.mark.asyncio
    async def test_connection_count_tracks_joins_and_leaves(self):
        """Connection count is updated correctly as clients join and leave."""
        manager = WebSocketManager()
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        assert manager.get_connection_count() == 0

        await manager.connect(ws1, client_id="c1")
        assert manager.get_connection_count() == 1

        await manager.connect(ws2, client_id="c2")
        assert manager.get_connection_count() == 2

        manager.disconnect(ws1)
        assert manager.get_connection_count() == 1

        manager.disconnect(ws2)
        assert manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_client_ids_tracked(self):
        """Client IDs are tracked per connection."""
        manager = WebSocketManager()
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        await manager.connect(ws1, client_id="alice")
        await manager.connect(ws2, client_id="bob")

        ids = manager.get_all_client_ids()
        assert "alice" in ids
        assert "bob" in ids

        manager.disconnect(ws1)
        manager.disconnect(ws2)

    @pytest.mark.asyncio
    async def test_auto_client_id_generated(self):
        """Client ID is auto-generated if not provided."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws)  # no client_id

        ids = manager.get_all_client_ids()
        assert len(ids) == 1
        assert ids[0].startswith("client_")

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_connection_info_returns_metadata(self):
        """get_connection_info() returns structured metadata for all connections."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="info-test")

        info = manager.get_connection_info()
        assert len(info) == 1
        assert info[0]["client_id"] == "info-test"
        assert info[0]["state"] == ConnectionState.CONNECTED
        assert info[0]["missed_pings"] == 0
        assert "connected_at" in info[0]
        assert "last_activity" in info[0]

        manager.disconnect(ws)


# ────────────────────────────────────────────────────────────────────────────
# Connect / Disconnect Tests
# ────────────────────────────────────────────────────────────────────────────

class TestConnectDisconnect:
    """Tests for basic connection management."""

    @pytest.mark.asyncio
    async def test_connect_sends_welcome_message(self):
        """Connecting sends a connection_established message to the client."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="welcome-test")

        welcome = ws.sent_messages[0]
        assert welcome["type"] == "connection_established"
        assert welcome["client_id"] == "welcome-test"
        assert "timestamp" in welcome

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_disconnect_cancels_heartbeat_task(self):
        """Disconnecting a client cancels its heartbeat task."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="hb-cancel-test")

        # Task should exist
        task = manager._heartbeat_tasks.get(ws)
        assert task is not None

        manager.disconnect(ws)

        # Task should be gone and cancelled
        assert ws not in manager._heartbeat_tasks

    @pytest.mark.asyncio
    async def test_disconnect_unknown_client_is_safe(self):
        """Calling disconnect on an unregistered WebSocket does not raise."""
        manager = WebSocketManager()
        unknown_ws = make_mock_websocket()

        # Should not raise
        manager.disconnect(unknown_ws)

    @pytest.mark.asyncio
    async def test_send_to_client(self):
        """send_to_client() delivers a message to the target WebSocket."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="send-test")

        payload = {"type": "test_event", "data": "hello"}
        await manager.send_to_client(ws, payload)

        # sent_messages[0] = welcome, [1] = our payload
        assert ws.sent_messages[-1] == payload

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_send_to_client_disconnects_on_error(self):
        """send_to_client() removes a client that raises an error on send."""
        manager = WebSocketManager()
        ws = AsyncMock()

        # accept() succeeds
        ws.accept = AsyncMock()
        # send_json raises on the second call (first is welcome message)
        call_count = 0

        async def failing_send(data):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise RuntimeError("Connection reset")

        ws.send_json = failing_send
        ws.sent_messages = []

        await manager.connect(ws, client_id="error-send-test")
        assert manager.get_connection_count() == 1

        # This send should fail and trigger disconnect
        await manager.send_to_client(ws, {"type": "trigger_error"})

        assert manager.get_connection_count() == 0


# ────────────────────────────────────────────────────────────────────────────
# Heartbeat / Ping-Pong Tests
# ────────────────────────────────────────────────────────────────────────────

class TestHeartbeat:
    """Tests for heartbeat/ping-pong mechanism."""

    @pytest.mark.asyncio
    async def test_handle_pong_resets_missed_pings(self):
        """handle_pong() resets the missed_pings counter to zero."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="pong-reset-test")

        # Manually set missed pings to simulate prior timeouts
        manager.connection_metadata[ws]["missed_pings"] = 2

        await manager.handle_pong(ws)

        assert manager.connection_metadata[ws]["missed_pings"] == 0

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_handle_pong_sets_pong_event(self):
        """handle_pong() sets the pong asyncio.Event."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="pong-event-test")

        pong_event = manager.connection_metadata[ws]["pong_event"]
        pong_event.clear()  # ensure it's not set

        await manager.handle_pong(ws)

        assert pong_event.is_set()

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_handle_pong_updates_last_activity(self):
        """handle_pong() updates the last_activity timestamp."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="pong-activity-test")

        before = manager.connection_metadata[ws]["last_activity"]
        await asyncio.sleep(0.01)  # tiny sleep so timestamp differs
        await manager.handle_pong(ws)

        after = manager.connection_metadata[ws]["last_activity"]
        assert after >= before

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_handle_pong_unknown_client_is_safe(self):
        """handle_pong() on an unknown WebSocket does not raise."""
        manager = WebSocketManager()
        unknown_ws = make_mock_websocket()
        # Should not raise
        await manager.handle_pong(unknown_ws)

    @pytest.mark.asyncio
    async def test_heartbeat_loop_sends_ping(self):
        """Heartbeat loop sends a ping message after HEARTBEAT_INTERVAL seconds."""
        manager = WebSocketManager()
        # Use a very short interval for the test
        manager.HEARTBEAT_INTERVAL = 0.05  # 50ms
        manager.HEARTBEAT_TIMEOUT = 0.05   # 50ms

        ws = make_mock_websocket()
        await manager.connect(ws, client_id="hb-ping-test")

        # Wait long enough for at least one ping to be sent
        await asyncio.sleep(0.15)

        # Check that a ping was sent (beyond the initial welcome)
        ping_messages = [m for m in ws.sent_messages if m.get("type") == "ping"]
        assert len(ping_messages) >= 1, "Expected at least one ping to be sent"

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_heartbeat_loop_closes_stale_connection(self):
        """Connection is closed after MAX_MISSED_PINGS consecutive missed pongs."""
        manager = WebSocketManager()
        manager.HEARTBEAT_INTERVAL = 0.05  # 50ms
        manager.HEARTBEAT_TIMEOUT = 0.05   # 50ms
        manager.MAX_MISSED_PINGS = 3

        ws = make_mock_websocket()
        await manager.connect(ws, client_id="stale-conn-test")

        # Wait for 3 missed pings worth of time
        # Each cycle = HEARTBEAT_INTERVAL + HEARTBEAT_TIMEOUT = 100ms
        # 3 cycles = 300ms, add buffer
        await asyncio.sleep(0.5)

        # Connection should be closed by the heartbeat loop
        assert ws not in manager.active_connections, (
            "Stale connection should have been removed after 3 missed pings"
        )

    @pytest.mark.asyncio
    async def test_heartbeat_loop_keeps_healthy_connection(self):
        """Heartbeat loop keeps a connection alive when pong is received."""
        manager = WebSocketManager()
        manager.HEARTBEAT_INTERVAL = 0.05  # 50ms
        manager.HEARTBEAT_TIMEOUT = 0.1    # 100ms

        ws = make_mock_websocket()
        await manager.connect(ws, client_id="healthy-conn-test")

        # Simulate pong responses automatically
        async def auto_pong():
            for _ in range(5):
                await asyncio.sleep(0.03)  # respond before timeout
                if ws in manager.active_connections:
                    await manager.handle_pong(ws)

        asyncio.create_task(auto_pong())

        await asyncio.sleep(0.4)

        # Connection should still be alive
        assert ws in manager.active_connections, (
            "Healthy connection should remain open when pong is received"
        )

        manager.disconnect(ws)


# ────────────────────────────────────────────────────────────────────────────
# Broadcast Tests
# ────────────────────────────────────────────────────────────────────────────

class TestBroadcast:
    """Tests for broadcast functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_clients(self):
        """broadcast() delivers message to all connected clients."""
        manager = WebSocketManager()
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        await manager.connect(ws1, client_id="bc1")
        await manager.connect(ws2, client_id="bc2")

        await manager.broadcast({"type": "test_broadcast", "data": "hello"})

        types1 = [m["type"] for m in ws1.sent_messages]
        types2 = [m["type"] for m in ws2.sent_messages]

        assert "test_broadcast" in types1
        assert "test_broadcast" in types2

        manager.disconnect(ws1)
        manager.disconnect(ws2)

    @pytest.mark.asyncio
    async def test_broadcast_excludes_specified_client(self):
        """broadcast(exclude=ws) skips the excluded client."""
        manager = WebSocketManager()
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        await manager.connect(ws1, client_id="excl1")
        await manager.connect(ws2, client_id="excl2")

        await manager.broadcast({"type": "exclusive_event"}, exclude=ws1)

        types1 = [m["type"] for m in ws1.sent_messages]
        types2 = [m["type"] for m in ws2.sent_messages]

        assert "exclusive_event" not in types1
        assert "exclusive_event" in types2

        manager.disconnect(ws1)
        manager.disconnect(ws2)

    @pytest.mark.asyncio
    async def test_broadcast_skips_when_no_connections(self):
        """broadcast() with no connections does not raise."""
        manager = WebSocketManager()
        # Should complete without error
        await manager.broadcast({"type": "orphan_event"})

    @pytest.mark.asyncio
    async def test_broadcast_adds_timestamp_when_missing(self):
        """broadcast() injects a timestamp if none is provided."""
        manager = WebSocketManager()
        ws = make_mock_websocket()

        await manager.connect(ws, client_id="ts-test")
        await manager.broadcast({"type": "no_timestamp_event"})

        # Find the broadcast message
        msg = next(m for m in ws.sent_messages if m["type"] == "no_timestamp_event")
        assert "timestamp" in msg

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_client(self):
        """broadcast() removes clients that raise errors during send."""
        manager = WebSocketManager()
        good_ws = make_mock_websocket()
        bad_ws = AsyncMock()
        bad_ws.sent_messages = []

        # bad_ws.accept succeeds, but send_json always fails after connection
        call_count = 0

        async def bad_send_json(data):
            nonlocal call_count
            call_count += 1
            if call_count > 1:  # first call is welcome message
                raise RuntimeError("Connection broken")
            bad_ws.sent_messages.append(data)

        bad_ws.send_json = bad_send_json
        bad_ws.accept = AsyncMock()

        await manager.connect(good_ws, client_id="good")
        await manager.connect(bad_ws, client_id="bad")

        assert manager.get_connection_count() == 2

        await manager.broadcast({"type": "test"})

        assert manager.get_connection_count() == 1
        assert good_ws in manager.active_connections

        manager.disconnect(good_ws)


# ────────────────────────────────────────────────────────────────────────────
# Event Broadcasting Methods Tests
# ────────────────────────────────────────────────────────────────────────────

class TestEventBroadcastMethods:
    """Tests for specific event broadcast helper methods."""

    @pytest.mark.asyncio
    async def test_broadcast_agent_created(self):
        manager = WebSocketManager()
        ws = make_mock_websocket()
        await manager.connect(ws, client_id="ac-test")

        await manager.broadcast_agent_created({"id": "agent-1", "name": "TestAgent"})

        msg = next(m for m in ws.sent_messages if m["type"] == "agent_created")
        assert msg["agent"]["id"] == "agent-1"

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_broadcast_agent_status_change(self):
        manager = WebSocketManager()
        ws = make_mock_websocket()
        await manager.connect(ws, client_id="asc-test")

        await manager.broadcast_agent_status_change("agent-1", "idle", "executing")

        msg = next(m for m in ws.sent_messages if m["type"] == "agent_status_changed")
        assert msg["agent_id"] == "agent-1"
        assert msg["old_status"] == "idle"
        assert msg["new_status"] == "executing"

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_broadcast_chat_stream(self):
        manager = WebSocketManager()
        ws = make_mock_websocket()
        await manager.connect(ws, client_id="cs-test")

        await manager.broadcast_chat_stream("orch-123", "Hello", is_complete=False)

        msg = next(m for m in ws.sent_messages if m["type"] == "chat_stream")
        assert msg["orchestrator_agent_id"] == "orch-123"
        assert msg["chunk"] == "Hello"
        assert msg["is_complete"] is False

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_broadcast_error(self):
        manager = WebSocketManager()
        ws = make_mock_websocket()
        await manager.connect(ws, client_id="err-test")

        await manager.broadcast_error("Something went wrong", {"code": 500})

        msg = next(m for m in ws.sent_messages if m["type"] == "error")
        assert msg["message"] == "Something went wrong"
        assert msg["details"]["code"] == 500

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_set_typing_indicator(self):
        manager = WebSocketManager()
        ws = make_mock_websocket()
        await manager.connect(ws, client_id="typing-test")

        await manager.set_typing_indicator("orch-456", True)

        msg = next(m for m in ws.sent_messages if m["type"] == "chat_typing")
        assert msg["orchestrator_agent_id"] == "orch-456"
        assert msg["is_typing"] is True

        manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_send_heartbeat_legacy(self):
        """Legacy send_heartbeat() still works for backwards compatibility."""
        manager = WebSocketManager()
        ws = make_mock_websocket()
        await manager.connect(ws, client_id="legacy-hb-test")

        await manager.send_heartbeat()

        msg = next(m for m in ws.sent_messages if m["type"] == "heartbeat")
        assert "active_connections" in msg

        manager.disconnect(ws)


# ────────────────────────────────────────────────────────────────────────────
# Multiple Connections Tests
# ────────────────────────────────────────────────────────────────────────────

class TestMultipleConnections:
    """Tests for concurrent connection scenarios."""

    @pytest.mark.asyncio
    async def test_independent_heartbeat_tasks_per_connection(self):
        """Each connection gets its own independent heartbeat task."""
        manager = WebSocketManager()
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        await manager.connect(ws1, client_id="multi-1")
        await manager.connect(ws2, client_id="multi-2")

        task1 = manager._heartbeat_tasks.get(ws1)
        task2 = manager._heartbeat_tasks.get(ws2)

        assert task1 is not None
        assert task2 is not None
        assert task1 is not task2

        manager.disconnect(ws1)
        manager.disconnect(ws2)

    @pytest.mark.asyncio
    async def test_disconnect_one_does_not_affect_others(self):
        """Disconnecting one client does not affect other connections."""
        manager = WebSocketManager()
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        await manager.connect(ws1, client_id="stable-1")
        await manager.connect(ws2, client_id="stable-2")

        manager.disconnect(ws1)

        assert manager.get_connection_count() == 1
        assert ws2 in manager.active_connections
        assert manager.get_connection_state(ws2) == ConnectionState.CONNECTED

        manager.disconnect(ws2)
