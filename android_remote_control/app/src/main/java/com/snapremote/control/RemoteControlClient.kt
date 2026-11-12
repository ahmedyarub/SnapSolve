package com.snapremote.control

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Listener interface for receiving push-based events from the SnapSolve server.
 *
 * All callbacks are invoked on OkHttp's background thread — callers must dispatch
 * to the main thread (e.g. via `runOnUiThread`) before touching the UI.
 */
/** Outcome of [RemoteControlClient.testConnection]. */
enum class ConnectionCheck { OK, UNAUTHORIZED, UNREACHABLE }

interface RemoteControlListener {
    /** Called when the WebSocket connection is established and the server acknowledged. */
    fun onConnected()

    /** Called when the WebSocket connection is lost or explicitly closed. */
    fun onDisconnected(reason: String)

    /** Called when the server pushes a UI state update. */
    fun onStateUpdate(
        buttons: JSONObject?,
        hasNewResponseImage: Boolean,
        transcriptionLanguage: String?,
        periodicScreenshotsEnabled: Boolean?,
    )

    /** Called when a network or protocol error occurs. */
    fun onError(message: String)
}

/**
 * Client that communicates with the SnapSolve remote control server.
 *
 * Uses a persistent **WebSocket** connection for all commands (mouse, actions,
 * keyboard, connect/disconnect) and **HTTP GET** for the initial health check
 * (`/status`) and response image downloads (`/response_image`).
 *
 * ## Threading
 * - [testConnection] and [fetchResponseImage] are blocking HTTP calls — call
 *   them from `Dispatchers.IO`.
 * - All other methods send fire-and-forget JSON messages over the WebSocket
 *   and return immediately.
 * - Push events (state updates, disconnections) are delivered via
 *   [RemoteControlListener] on OkHttp's background thread.
 */
class RemoteControlClient {

    private var serverIp: String = ""
    private var serverPort: Int = 3031
    private var apiKey: String = ""

    /** Shared OkHttpClient with sensible timeouts for a local-network connection. */
    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .build()

    /** The active WebSocket connection, or `null` if disconnected. */
    private var webSocket: WebSocket? = null

    /** Listener for push-based server events. */
    private var listener: RemoteControlListener? = null

    // -------------------------------------------------------------------------
    // Configuration
    // -------------------------------------------------------------------------

    /**
     * Update the server address. Must be called before any network request.
     *
     * @param ip   IPv4/IPv6 address or hostname of the SnapSolve host.
     * @param port TCP port the SnapSolve remote control server is listening on.
     * @param key  API key from the desktop's pairing dialog; sent with every request.
     */
    fun setServerConfig(ip: String, port: Int, key: String) {
        serverIp = ip
        serverPort = port
        apiKey = key
    }

    /** A request to [url] carrying the API key the server requires. */
    private fun authorizedRequest(url: String): Request.Builder =
        Request.Builder().url(url).header("Authorization", apiKey)

    /**
     * Register a listener for push-based server events.
     *
     * @param listener Callback receiver, or `null` to unregister.
     */
    fun setListener(listener: RemoteControlListener?) {
        this.listener = listener
    }

    /** Returns the base HTTP URL, e.g. `http://192.168.1.10:8080`. */
    private fun baseUrl(): String = "http://$serverIp:$serverPort"

    /** Returns the WebSocket URL, e.g. `ws://192.168.1.10:3031/ws`. */
    private fun wsUrl(): String = "ws://$serverIp:$serverPort/ws"

    // -------------------------------------------------------------------------
    // HTTP methods (connection test + image fetch)
    // -------------------------------------------------------------------------

    /**
     * Verify that the SnapSolve server is reachable by querying `GET /status`.
     *
     * This is a plain HTTP request (not WebSocket) and must be called from a
     * background thread.
     *
     * @return [ConnectionCheck.OK] on HTTP 200, [ConnectionCheck.UNAUTHORIZED] when
     *   the server rejects the key, [ConnectionCheck.UNREACHABLE] otherwise.
     */
    fun testConnection(): ConnectionCheck = try {
        val request = authorizedRequest("${baseUrl()}/status").get().build()
        httpClient.newCall(request).execute().use {
            when {
                it.isSuccessful -> ConnectionCheck.OK
                it.code == 401 -> ConnectionCheck.UNAUTHORIZED
                else -> ConnectionCheck.UNREACHABLE
            }
        }
    } catch (e: IOException) {
        ConnectionCheck.UNREACHABLE
    }

    /**
     * Fetch the response screenshot image bytes via `GET /response_image`.
     *
     * This is a plain HTTP request and must be called from a background thread.
     *
     * @return `ByteArray` containing the PNG image if successful, `null` otherwise.
     */
    fun fetchResponseImage(): ByteArray? = try {
        val request = authorizedRequest("${baseUrl()}/response_image").get().build()
        httpClient.newCall(request).execute().use { response ->
            if (response.isSuccessful) {
                response.body?.bytes()
            } else {
                null
            }
        }
    } catch (e: Exception) {
        null
    }

    // -------------------------------------------------------------------------
    // WebSocket connection
    // -------------------------------------------------------------------------

    /**
     * Open a WebSocket connection to the server and send a `connect` message.
     *
     * The connection is established asynchronously; results are delivered via
     * [RemoteControlListener.onConnected] or [RemoteControlListener.onError].
     */
    fun connect() {
        val request = authorizedRequest(wsUrl()).build()

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                // Send the connect message to block the physical mouse on the server
                send(JSONObject().put("type", "connect"))
                listener?.onConnected()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleServerMessage(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                this@RemoteControlClient.webSocket = null
                listener?.onDisconnected(reason.ifEmpty { "Connection closed" })
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                this@RemoteControlClient.webSocket = null
                // The server refuses the handshake (HTTP 403) when the API key is wrong.
                val reason = if (response?.code == 403) "API key rejected" else t.message
                listener?.onDisconnected(reason ?: "Connection failed")
            }
        })
    }

    /**
     * Send a `disconnect` message and close the WebSocket connection.
     */
    fun disconnect() {
        send(JSONObject().put("type", "disconnect"))
        webSocket?.close(1000, "Client disconnecting")
        webSocket = null
    }

    /** Whether the WebSocket is currently open. */
    val isConnected: Boolean
        get() = webSocket != null

    // -------------------------------------------------------------------------
    // WebSocket commands (fire-and-forget)
    // -------------------------------------------------------------------------

    /**
     * Trigger a named SnapSolve action (e.g. `"capture"`, `"reselect"`, `"cancel"`).
     *
     * @param action Action identifier recognised by the server.
     * @return `true` if the message was enqueued.
     */
    fun executeAction(action: String): Boolean =
        send(JSONObject().put("type", "action").put("action", action))

    /**
     * Move the mouse cursor by relative screen coordinates.
     *
     * @param dx Horizontal delta (normalised).
     * @param dy Vertical delta (normalised).
     * @return `true` if the message was enqueued.
     */
    fun moveMouse(dx: Float, dy: Float): Boolean =
        send(JSONObject().put("type", "mouse_move").put("dx", dx).put("dy", dy))

    /**
     * Send a single mouse button click at the current cursor position.
     *
     * @param button `"left"` (default), `"right"`, or `"middle"`.
     * @return `true` if the message was enqueued.
     */
    fun clickMouse(button: String = "left"): Boolean =
        send(JSONObject().put("type", "mouse_click").put("button", button))

    /**
     * Send a double mouse button click at the current cursor position.
     *
     * @param button `"left"` (default), `"right"`, or `"middle"`.
     * @return `true` if the message was enqueued.
     */
    fun doubleClickMouse(button: String = "left"): Boolean =
        send(JSONObject().put("type", "mouse_double_click").put("button", button))

    /**
     * Press and hold the mouse button to begin a drag operation.
     *
     * @return `true` if the message was enqueued.
     */
    fun startDrag(): Boolean =
        send(JSONObject().put("type", "mouse_drag_start"))

    /**
     * Release the mouse button to finish a drag operation.
     *
     * @return `true` if the message was enqueued.
     */
    fun endDrag(): Boolean =
        send(JSONObject().put("type", "mouse_drag_end"))

    /**
     * Scroll the mouse wheel at the current cursor position.
     *
     * @param delta Number of scroll clicks. Positive = up, negative = down.
     * @return `true` if the message was enqueued.
     */
    fun scrollMouse(delta: Int): Boolean =
        send(JSONObject().put("type", "mouse_scroll").put("delta", delta))

    /**
     * Send text to be typed by the main app.
     *
     * @param text The text to type.
     * @return `true` if the message was enqueued.
     */
    fun typeText(text: String): Boolean =
        send(JSONObject().put("type", "keyboard_type").put("text", text))

    /**
     * Acknowledge receipt of the response image so the server clears the flag.
     *
     * @return `true` if the message was enqueued.
     */
    fun ackResponseImage(): Boolean =
        send(JSONObject().put("type", "response_image_ack"))

    /**
     * Set the transcription language on the server.
     *
     * @param language BCP-47 language code (e.g. "en", "es", "fr").
     * @return `true` if the message was enqueued.
     */
    fun setTranscriptionLanguage(language: String): Boolean =
        send(JSONObject().put("type", "set_transcription_language").put("language", language))

    // -------------------------------------------------------------------------
    // Internal
    // -------------------------------------------------------------------------

    /**
     * Send a JSON message over the WebSocket.
     *
     * @param payload JSON object to send.
     * @return `true` if the message was successfully enqueued by OkHttp.
     */
    private fun send(payload: JSONObject): Boolean {
        return webSocket?.send(payload.toString()) ?: false
    }

    /**
     * Parse and dispatch an incoming server message to the appropriate listener
     * callback.
     */
    private fun handleServerMessage(text: String) {
        try {
            val json = JSONObject(text)
            when (json.optString("type")) {
                "state_update" -> {
                    val buttons = json.optJSONObject("buttons")
                    val hasNewImage = json.optBoolean("has_new_response_image", false)
                    val transLang = if (json.has("transcription_language")) json.optString("transcription_language") else null
                    val periodicScreenshots = if (json.has("periodic_screenshots_enabled")) {
                        json.optBoolean("periodic_screenshots_enabled", false)
                    } else {
                        null
                    }
                    listener?.onStateUpdate(buttons, hasNewImage, transLang, periodicScreenshots)
                }

                "error" -> {
                    val message = json.optString("message", "Unknown error")
                    listener?.onError(message)
                }

                // "response" messages are fire-and-forget acknowledgements;
                // no action needed on the client side.
            }
        } catch (e: Exception) {
            // Malformed message — ignore
        }
    }
}