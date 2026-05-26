package com.snapremote.control

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * HTTP client that communicates with the SnapSolve remote control server.
 *
 * All public methods are `suspend` functions and must be called from a coroutine context
 * (e.g. `lifecycleScope.launch(Dispatchers.IO) { … }`). They return `true` on success
 * (HTTP 200) and `false` on any error.
 *
 * Thread-safety: [OkHttpClient] is fully thread-safe and reused across calls. The
 * mutable [serverIp] / [serverPort] fields are only written from the main thread via
 * [setServerConfig] before any request is dispatched, so no additional synchronisation
 * is required.
 */
class RemoteControlClient {

    private var serverIp: String = ""
    private var serverPort: Int = 8080

    /** Shared OkHttpClient with sensible timeouts for a local-network connection. */
    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .build()

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

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

    /** Returns the base URL for all endpoints, e.g. `http://192.168.1.10:8080`. */
    private fun baseUrl(): String = "http://$serverIp:$serverPort"

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /**
     * Execute a GET request and return `true` if the response code is 200.
     *
     * @param path URL path (e.g. `/status`).
     */
    private fun get(path: String): Boolean {
        val request = Request.Builder().url("${baseUrl()}$path").get().build()
        return httpClient.newCall(request).execute().use { it.isSuccessful }
    }

    /**
     * Execute a POST request with a JSON body and return `true` if the response code is 200.
     *
     * @param path    URL path (e.g. `/action`).
     * @param payload JSON object to send as the request body.
     */
    private fun post(path: String, payload: JSONObject): Boolean {
        val body = payload.toString().toRequestBody(jsonMediaType)
        val request = Request.Builder()
            .url("${baseUrl()}$path")
            .post(body)
            .build()
        return httpClient.newCall(request).execute().use { it.isSuccessful }
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Verify that the SnapSolve server is reachable by querying `/status`.
     *
     * @return `true` if the server responded with HTTP 200.
     */
    fun testConnection(): Boolean = try {
        get("/status")
    } catch (e: IOException) {
        false
    }

    /**
     * Notify the server that the Android client has connected.
     *
     * The server will block physical mouse input so that only the Android
     * touchpad controls the cursor.
     *
     * @return `true` if the server acknowledged the connection.
     */
    fun connect(): Boolean = try {
        post("/connect", JSONObject())
    } catch (e: IOException) {
        false
    }

    /**
     * Notify the server that the Android client is disconnecting.
     *
     * The server will restore physical mouse input.
     *
     * @return `true` if the server acknowledged the disconnection.
     */
    fun disconnect(): Boolean = try {
        post("/disconnect", JSONObject())
    } catch (e: IOException) {
        false
    }

    /**
     * Trigger a named SnapSolve action (e.g. `"capture"`, `"reselect"`, `"cancel"`).
     *
     * @param action Action identifier recognised by the server's `/action` endpoint.
     * @return `true` if the server responded with HTTP 200.
     */
    fun executeAction(action: String): Boolean = try {
        post("/action", JSONObject().put("action", action))
    } catch (e: IOException) {
        false
    }

    /**
     * Move the mouse cursor to a position expressed as relative screen coordinates.
     *
     * The server converts the (0–1) range to absolute pixel coordinates using the
     * host machine's screen resolution.
     *
     * @param x Horizontal position in the range [0.0, 1.0].
     * @param y Vertical position in the range [0.0, 1.0].
     * @return `true` on success.
     */
    fun moveMouse(x: Float, y: Float): Boolean = try {
        post("/mouse/move", JSONObject().put("x", x).put("y", y))
    } catch (e: IOException) {
        false
    }

    /**
     * Send a single mouse button click at the current cursor position.
     *
     * @param button `"left"` (default), `"right"`, or `"middle"`.
     * @return `true` on success.
     */
    fun clickMouse(button: String = "left"): Boolean = try {
        post("/mouse/click", JSONObject().put("button", button))
    } catch (e: IOException) {
        false
    }

    /**
     * Send a double mouse button click at the current cursor position.
     *
     * @param button `"left"` (default), `"right"`, or `"middle"`.
     * @return `true` on success.
     */
    fun doubleClickMouse(button: String = "left"): Boolean = try {
        post("/mouse/double_click", JSONObject().put("button", button))
    } catch (e: IOException) {
        false
    }

    /**
     * Press and hold the mouse button to begin a drag operation.
     *
     * @param x Relative X coordinate of the drag origin [0.0, 1.0].
     * @param y Relative Y coordinate of the drag origin [0.0, 1.0].
     * @return `true` on success.
     */
    fun startDrag(x: Float, y: Float): Boolean = try {
        post("/mouse/drag_start", JSONObject().put("x", x).put("y", y))
    } catch (e: IOException) {
        false
    }

    /**
     * Release the mouse button to finish a drag operation.
     *
     * @param x Relative X coordinate of the drag target [0.0, 1.0].
     * @param y Relative Y coordinate of the drag target [0.0, 1.0].
     * @return `true` on success.
     */
    fun endDrag(x: Float, y: Float): Boolean = try {
        post("/mouse/drag_end", JSONObject().put("x", x).put("y", y))
    } catch (e: IOException) {
        false
    }

    /**
     * Scroll the mouse wheel at the current cursor position.
     *
     * @param delta Number of scroll clicks. Positive = scroll up, negative = scroll down.
     * @return `true` on success.
     */
    fun scrollMouse(delta: Int): Boolean = try {
        post("/mouse/scroll", JSONObject().put("delta", delta))
    } catch (e: IOException) {
        false
    }
}