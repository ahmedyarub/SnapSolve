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
interface RemoteControlListener {
    /** Called when the WebSocket connection is established and the server acknowledged. */
    fun onConnected()

    /** Called when the WebSocket connection is lost or explicitly closed. */
    fun onDisconnected(reason: String)

    /** Called when the server pushes a UI state update. */
    fun onStateUpdate(buttons: JSONObject?, hasNewResponseImage: Boolean, transcriptionLanguage: String?)

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
    private var serverPort: Int = 8080

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
     */
    fun setServerConfig(ip: String, port: Int) {
        serverIp = ip
        serverPort = port
    }

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

    /** Returns the WebSocket URL, e.g. `ws://192.168.1.10:8080`. */
    private fun wsUrl(): String = "ws://$serverIp:$serverPort"

    // -------------------------------------------------------------------------
    // HTTP methods (connection test + image fetch)
    // -------------------------------------------------------------------------

    /**
     * Verify that the SnapSolve server is reachable by querying `GET /status`.
     *
     * This is a plain HTTP request (not WebSocket) and must be called from a
     * background thread.
     *
     * @return `true` if the server responded with HTTP 200.
     */
    fun testConnection(): Boolean = try {
        val request = Request.Builder().url("${baseUrl()}/status").get().build()
        httpClient.newCall(request).execute().use { it.isSuccessful }
    } catch (e: IOException) {
        false
    }

    /**
     * Fetch the response screenshot image bytes via `GET /response_image`.
     *
     * This is a plain HTTP request and must be called from a background thread.
     *
     * @return `ByteArray` containing the PNG image if successful, `null` otherwise.
     */
    fun fetchResponseImage(): ByteArray? = try {
        val request = Request.Builder().url("${baseUrl()}/response_image").get().build()
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
        val request = Request.Builder().url(wsUrl()).build()

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                // Send the connect message to block the physical mouse on the server
                send(JSONObject().put("type", "connect"))
                listener?.onConnected()
            }

            override fun onMessage(ws: WebSocket, text: String) {
                handleServerMessage(text)
            }

            override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                ws.close(1000, null)
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                webSocket = null
                listener?.onDisconnected(reason.ifEmpty { "Connection closed" })
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                webSocket = null
                listener?.onDisconnected(t.message ?: "Connection failed")
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
                    val transLang = json.optString("transcription_language", null)
                    listener?.onStateUpdate(buttons, hasNewImage, transLang)
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