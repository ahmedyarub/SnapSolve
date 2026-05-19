package com.snapsolve.remotecontrol

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

private const val CONTENT_TYPE = "Content-Type"
private const val APPLICATION_JSON = "application/json"

class RemoteControlClient {
    private var serverIp: String = ""
    private var serverPort: Int = 8080

    fun setServerConfig(ip: String, port: Int) {
        this.serverIp = ip
        this.serverPort = port
    }

    suspend fun testConnection(): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/status")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 5000
            connection.readTimeout = 5000

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun executeAction(action: String): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/action")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty(CONTENT_TYPE, APPLICATION_JSON)
            connection.doOutput = true

            val jsonPayload = JSONObject().apply {
                put("action", action)
            }

            val outputStream = OutputStreamWriter(connection.outputStream)
            outputStream.write(jsonPayload.toString())
            outputStream.flush()
            outputStream.close()

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun moveMouse(x: Float, y: Float): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/mouse/move")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty(CONTENT_TYPE, APPLICATION_JSON)
            connection.doOutput = true

            val jsonPayload = JSONObject().apply {
                put("x", x)
                put("y", y)
            }

            val outputStream = OutputStreamWriter(connection.outputStream)
            outputStream.write(jsonPayload.toString())
            outputStream.flush()
            outputStream.close()

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun clickMouse(button: String = "left"): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/mouse/click")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty(CONTENT_TYPE, APPLICATION_JSON)
            connection.doOutput = true

            val jsonPayload = JSONObject().apply {
                put("button", button)
            }

            val outputStream = OutputStreamWriter(connection.outputStream)
            outputStream.write(jsonPayload.toString())
            outputStream.flush()
            outputStream.close()

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun doubleClickMouse(button: String = "left"): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/mouse/double_click")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty(CONTENT_TYPE, APPLICATION_JSON)
            connection.doOutput = true

            val jsonPayload = JSONObject().apply {
                put("button", button)
            }

            val outputStream = OutputStreamWriter(connection.outputStream)
            outputStream.write(jsonPayload.toString())
            outputStream.flush()
            outputStream.close()

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun startDrag(x: Float, y: Float): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/mouse/drag_start")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty(CONTENT_TYPE, APPLICATION_JSON)
            connection.doOutput = true

            val jsonPayload = JSONObject().apply {
                put("x", x)
                put("y", y)
            }

            val outputStream = OutputStreamWriter(connection.outputStream)
            outputStream.write(jsonPayload.toString())
            outputStream.flush()
            outputStream.close()

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun endDrag(x: Float, y: Float): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/mouse/drag_end")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty(CONTENT_TYPE, APPLICATION_JSON)
            connection.doOutput = true

            val jsonPayload = JSONObject().apply {
                put("x", x)
                put("y", y)
            }

            val outputStream = OutputStreamWriter(connection.outputStream)
            outputStream.write(jsonPayload.toString())
            outputStream.flush()
            outputStream.close()

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    suspend fun scrollMouse(delta: Int): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val url = URL("http://$serverIp:$serverPort/mouse/scroll")
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty(CONTENT_TYPE, APPLICATION_JSON)
            connection.doOutput = true

            val jsonPayload = JSONObject().apply {
                put("delta", delta)
            }

            val outputStream = OutputStreamWriter(connection.outputStream)
            outputStream.write(jsonPayload.toString())
            outputStream.flush()
            outputStream.close()

            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }
}