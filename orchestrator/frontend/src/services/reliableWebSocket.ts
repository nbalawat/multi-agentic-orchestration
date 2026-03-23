/**
 * ReliableWebSocket Service
 *
 * Provides a resilient WebSocket wrapper with:
 * - Automatic reconnection with exponential backoff
 * - Message buffering during disconnection (replayed on reconnect)
 * - Heartbeat/ping-pong to detect and recover from stale connections
 * - Connection state tracking (connecting, connected, disconnected, error)
 */

import type { WebSocketCallbacks } from './chatService'

/** Connection state enum */
export enum ConnectionState {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  ERROR = 'error',
}

/** A buffered outgoing message */
interface BufferedMessage {
  data: string
  queuedAt: string
}

/**
 * ReliableWebSocket
 *
 * Drop-in replacement for the raw WebSocket used in the orchestrator store.
 * Wraps the native browser WebSocket with reliability features.
 */
export class ReliableWebSocket {
  // Connection
  private ws: WebSocket | null = null
  private url: string
  private callbacks: WebSocketCallbacks

  // Reconnection
  private reconnectAttempts = 0
  private readonly maxReconnectAttempts = 10
  private reconnectDelay = 1000        // ms — start at 1 second
  private readonly maxReconnectDelay = 30_000  // ms — cap at 30 seconds
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _intentionalClose = false    // set to true on manual disconnect()

  // Message buffer (outgoing messages queued while disconnected)
  private messageBuffer: BufferedMessage[] = []
  private readonly maxBufferSize = 100

  // Heartbeat / ping-pong
  private readonly heartbeatInterval = 30_000  // ms
  private readonly heartbeatTimeout = 10_000   // ms
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private pongTimer: ReturnType<typeof setTimeout> | null = null

  // State
  private _state: ConnectionState = ConnectionState.DISCONNECTED
  private stateListeners: Array<(state: ConnectionState) => void> = []

  constructor(url: string, callbacks: WebSocketCallbacks) {
    this.url = url
    this.callbacks = callbacks
  }

  // ──────────────────────────────────────────────────────────────────
  // Public API
  // ──────────────────────────────────────────────────────────────────

  /** Initiate connection */
  connect(): void {
    this._intentionalClose = false
    this._doConnect()
  }

  /** Gracefully close and stop all reconnection attempts */
  disconnect(): void {
    this._intentionalClose = true
    this._cleanup()
    this._setState(ConnectionState.DISCONNECTED)
  }

  /**
   * Send a raw JSON-serialisable object.
   * If not connected, the message is buffered and replayed on reconnection.
   */
  send(data: object): void {
    const serialised = JSON.stringify(data)

    if (this._state === ConnectionState.CONNECTED && this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(serialised)
        return
      } catch (err) {
        console.error('[ReliableWebSocket] send() failed, buffering message:', err)
      }
    }

    // Buffer for later
    if (this.messageBuffer.length >= this.maxBufferSize) {
      // Drop oldest to make room
      this.messageBuffer.shift()
      console.warn('[ReliableWebSocket] Buffer full — oldest message dropped')
    }
    this.messageBuffer.push({ data: serialised, queuedAt: new Date().toISOString() })
    console.debug(`[ReliableWebSocket] Message buffered (${this.messageBuffer.length}/${this.maxBufferSize})`)
  }

  /** Current connection state */
  get state(): ConnectionState {
    return this._state
  }

  /** Subscribe to state changes */
  onStateChange(listener: (state: ConnectionState) => void): void {
    this.stateListeners.push(listener)
  }

  // ──────────────────────────────────────────────────────────────────
  // Internal — connection lifecycle
  // ──────────────────────────────────────────────────────────────────

  private _doConnect(): void {
    this._setState(ConnectionState.CONNECTING)

    try {
      this.ws = new WebSocket(this.url)
      this.ws.onopen    = this._onOpen.bind(this)
      this.ws.onmessage = this._onMessage.bind(this)
      this.ws.onerror   = this._onError.bind(this)
      this.ws.onclose   = this._onClose.bind(this)
    } catch (err) {
      console.error('[ReliableWebSocket] Failed to create WebSocket:', err)
      this._setState(ConnectionState.ERROR)
      this._scheduleReconnect()
    }
  }

  private _onOpen(): void {
    console.log('[ReliableWebSocket] Connected')
    this._setState(ConnectionState.CONNECTED)

    // Reset reconnection state
    this.reconnectAttempts = 0
    this.reconnectDelay = 1000

    // Replay buffered messages before notifying the caller
    this._replayBuffer()

    // Start heartbeat
    this._startHeartbeat()

    // Notify caller
    this.callbacks.onConnected?.()
  }

  private _onMessage(event: MessageEvent): void {
    try {
      const message = JSON.parse(event.data as string)

      // ── Handle ping-pong internally ───────────────────────────────
      if (message.type === 'ping') {
        // Server sent a ping — reply with pong
        this._sendRaw(JSON.stringify({
          type: 'pong',
          timestamp: message.timestamp,
          client_timestamp: new Date().toISOString(),
        }))
        return
      }

      if (message.type === 'pong') {
        // Server acknowledged our heartbeat ping
        this._handlePong()
        return
      }

      if (message.type === 'heartbeat') {
        // Legacy heartbeat broadcast — ignore silently
        return
      }

      // ── Route to caller callbacks ─────────────────────────────────
      this._routeMessage(message)

    } catch (err) {
      console.error('[ReliableWebSocket] Failed to parse message:', err)
    }
  }

  private _onError(_event: Event): void {
    console.error('[ReliableWebSocket] WebSocket error')
    this._setState(ConnectionState.ERROR)
    // onerror is always followed by onclose, so reconnection is handled there
  }

  private _onClose(event: CloseEvent): void {
    console.log(`[ReliableWebSocket] Closed — code=${event.code} reason="${event.reason}"`)

    this._stopHeartbeat()

    if (this._intentionalClose) {
      this._setState(ConnectionState.DISCONNECTED)
      this.callbacks.onDisconnected?.()
      return
    }

    this._setState(ConnectionState.DISCONNECTED)
    this.callbacks.onDisconnected?.()
    this._scheduleReconnect()
  }

  // ──────────────────────────────────────────────────────────────────
  // Internal — reconnection
  // ──────────────────────────────────────────────────────────────────

  private _scheduleReconnect(): void {
    if (this._intentionalClose) return

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error(
        `[ReliableWebSocket] Max reconnect attempts (${this.maxReconnectAttempts}) reached`
      )
      this._setState(ConnectionState.ERROR)
      this.callbacks.onError({ message: 'Max reconnect attempts reached' })
      return
    }

    this.reconnectAttempts++
    const delay = this.reconnectDelay
    console.log(
      `[ReliableWebSocket] Reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`
    )

    this.reconnectTimer = setTimeout(() => {
      if (!this._intentionalClose) {
        this._doConnect()
      }
    }, delay)

    // Exponential backoff for next attempt
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay)
  }

  // ──────────────────────────────────────────────────────────────────
  // Internal — message buffer
  // ──────────────────────────────────────────────────────────────────

  private _replayBuffer(): void {
    if (this.messageBuffer.length === 0) return

    console.log(`[ReliableWebSocket] Replaying ${this.messageBuffer.length} buffered messages`)
    const toSend = [...this.messageBuffer]
    this.messageBuffer = []

    for (const msg of toSend) {
      this._sendRaw(msg.data)
    }
  }

  private _sendRaw(serialised: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(serialised)
      } catch (err) {
        console.error('[ReliableWebSocket] _sendRaw failed:', err)
      }
    }
  }

  // ──────────────────────────────────────────────────────────────────
  // Internal — heartbeat
  // ──────────────────────────────────────────────────────────────────

  private _startHeartbeat(): void {
    this._stopHeartbeat()

    this.heartbeatTimer = setInterval(() => {
      this._sendPing()
    }, this.heartbeatInterval)
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    this._clearPongTimer()
  }

  private _sendPing(): void {
    if (this._state !== ConnectionState.CONNECTED) return

    this._sendRaw(JSON.stringify({
      type: 'ping',
      timestamp: new Date().toISOString(),
    }))

    // Wait for pong; if none arrives, treat connection as stale
    this.pongTimer = setTimeout(() => {
      console.warn('[ReliableWebSocket] Pong timeout — connection appears stale, reconnecting')
      this._cleanup()
      this._setState(ConnectionState.DISCONNECTED)
      this._scheduleReconnect()
    }, this.heartbeatTimeout)
  }

  private _handlePong(): void {
    this._clearPongTimer()
    console.debug('[ReliableWebSocket] Pong received — connection healthy')
  }

  private _clearPongTimer(): void {
    if (this.pongTimer !== null) {
      clearTimeout(this.pongTimer)
      this.pongTimer = null
    }
  }

  // ──────────────────────────────────────────────────────────────────
  // Internal — state & cleanup
  // ──────────────────────────────────────────────────────────────────

  private _setState(state: ConnectionState): void {
    this._state = state
    for (const listener of this.stateListeners) {
      try { listener(state) } catch { /* ignore listener errors */ }
    }
  }

  private _cleanup(): void {
    // Cancel pending reconnect timer
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    this._stopHeartbeat()

    // Close raw WebSocket without triggering reconnection logic
    if (this.ws) {
      this.ws.onopen    = null
      this.ws.onmessage = null
      this.ws.onerror   = null
      this.ws.onclose   = null
      if (
        this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING
      ) {
        this.ws.close()
      }
      this.ws = null
    }
  }

  // ──────────────────────────────────────────────────────────────────
  // Internal — message routing (same as original chatService)
  // ──────────────────────────────────────────────────────────────────

  private _routeMessage(message: any): void {
    switch (message.type) {
      case 'chat_stream':
        this.callbacks.onChatStream(
          message.chunk || '',
          message.is_complete || false
        )
        break

      case 'chat_typing':
        this.callbacks.onTyping(message.is_typing || false)
        break

      case 'agent_log':
        this.callbacks.onAgentLog?.(message)
        break

      case 'orchestrator_chat':
        this.callbacks.onOrchestratorChat?.(message)
        break

      case 'thinking_block':
        this.callbacks.onThinkingBlock?.(message)
        break

      case 'tool_use_block':
        this.callbacks.onToolUseBlock?.(message)
        break

      case 'agent_created':
        this.callbacks.onAgentCreated?.(message)
        break

      case 'agent_updated':
        this.callbacks.onAgentUpdated?.(message)
        break

      case 'agent_deleted':
        this.callbacks.onAgentDeleted?.(message)
        break

      case 'agent_status_changed':
        this.callbacks.onAgentStatusChange?.(message)
        break

      case 'agent_summary_update':
        this.callbacks.onAgentSummaryUpdate?.(message)
        break

      case 'orchestrator_updated':
        this.callbacks.onOrchestratorUpdated?.(message)
        break

      case 'ask_user_question':
        this.callbacks.onAskUserQuestion?.(message)
        break

      case 'feature_started':
        this.callbacks.onFeatureStarted?.(message)
        break

      case 'feature_merged':
        this.callbacks.onFeatureMerged?.(message)
        break

      case 'feature_merge_failed':
        this.callbacks.onFeatureMergeFailed?.(message)
        break

      case 'dag_progress':
        this.callbacks.onDagProgress?.(message)
        break

      case 'wave_transition':
        this.callbacks.onWaveTransition?.(message)
        break

      case 'dag_complete':
        this.callbacks.onDagComplete?.(message)
        break

      case 'error':
        this.callbacks.onError(message)
        break

      case 'connection_established':
        console.log('[ReliableWebSocket] Connection established:', message.client_id)
        break

      default:
        console.debug('[ReliableWebSocket] Unknown message type:', message.type)
    }
  }
}
