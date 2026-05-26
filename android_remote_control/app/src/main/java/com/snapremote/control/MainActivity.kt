package com.snapremote.control

import android.content.SharedPreferences
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Main (and only) Activity for SnapSolve Remote Control.
 *
 * ## Responsibilities
 * - Render the connection bar (IP, port, Connect button) and restore the last used
 *   address from [SharedPreferences] so the user does not have to retype it.
 * - Manage connection state: enable/disable action buttons and update the status bar.
 * - Forward button taps to the server via [RemoteControlClient].
 * - Wire the [TouchpadView] to the [RemoteControlClient] so touch events are sent
 *   directly to the server without routing through this Activity.
 *
 * ## Threading
 * All network calls are dispatched via [lifecycleScope] on [Dispatchers.IO] so they
 * are automatically canceled when the Activity is destroyed and never touch the UI
 * from a background thread.
 */
class MainActivity : AppCompatActivity() {

    // -------------------------------------------------------------------------
    // Views
    // -------------------------------------------------------------------------

    private lateinit var ipAddressEditText: EditText
    private lateinit var portEditText: EditText
    private lateinit var connectButton: Button
    private lateinit var statusTextView: TextView
    private lateinit var touchpadView: TouchpadView

    // Action buttons
    private lateinit var captureButton: MaterialButton
    private lateinit var reselectButton: MaterialButton
    private lateinit var multiCaptureButton: MaterialButton
    private lateinit var endMultiButton: MaterialButton
    private lateinit var toggleStitchingButton: MaterialButton
    private lateinit var cycleSourceButton: MaterialButton
    private lateinit var togglePanelButton: MaterialButton
    private lateinit var newChatButton: MaterialButton
    private lateinit var cancelButton: MaterialButton

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    private lateinit var remoteControlClient: RemoteControlClient
    private lateinit var prefs: SharedPreferences

    /** Whether the client is currently connected to the server. */
    private var isConnected = false

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getPreferences(MODE_PRIVATE)
        remoteControlClient = RemoteControlClient()

        bindViews()
        restoreSavedAddress()
        setupConnectButton()
        setupActionButtons()
        setConnected(false) // Start in disconnected state
        attemptAutoConnect()
    }

    // -------------------------------------------------------------------------
    // View binding
    // -------------------------------------------------------------------------

    /** Locate all views by ID and store references. */
    private fun bindViews() {
        ipAddressEditText = findViewById(R.id.ipAddressEditText)
        portEditText = findViewById(R.id.portEditText)
        connectButton = findViewById(R.id.connectButton)
        statusTextView = findViewById(R.id.statusTextView)
        touchpadView = findViewById(R.id.touchpadView)

        captureButton = findViewById(R.id.captureButton)
        reselectButton = findViewById(R.id.reselectButton)
        multiCaptureButton = findViewById(R.id.multiCaptureButton)
        endMultiButton = findViewById(R.id.endMultiButton)
        toggleStitchingButton = findViewById(R.id.toggleStitchingButton)
        cycleSourceButton = findViewById(R.id.cycleSourceButton)
        togglePanelButton = findViewById(R.id.togglePanelButton)
        newChatButton = findViewById(R.id.newChatButton)
        cancelButton = findViewById(R.id.cancelButton)

        touchpadView.setRemoteControlClient(remoteControlClient)
    }

    // -------------------------------------------------------------------------
    // Persistence
    // -------------------------------------------------------------------------

    /** Restore the last IP and port from SharedPreferences. */
    private fun restoreSavedAddress() {
        val savedIp = prefs.getString(getString(R.string.pref_key_ip), "") ?: ""
        val savedPort = prefs.getInt(getString(R.string.pref_key_port), 8080)
        ipAddressEditText.setText(savedIp)
        portEditText.setText(savedPort.toString())
    }

    /** Persist the current IP and port to SharedPreferences. */
    private fun saveAddress(ip: String, port: Int) {
        prefs.edit {
            putString(getString(R.string.pref_key_ip), ip)
                .putInt(getString(R.string.pref_key_port), port)
        }
    }

    /**
     * If a non-empty IP address was previously saved, automatically
     * attempt to connect so the user does not have to tap "Connect"
     * every time the app is launched.
     */
    private fun attemptAutoConnect() {
        val savedIp = ipAddressEditText.text.toString().trim()
        if (savedIp.isNotEmpty()) {
            connectToServer()
        }
    }

    // -------------------------------------------------------------------------
    // Connection
    // -------------------------------------------------------------------------

    private fun setupConnectButton() {
        connectButton.setOnClickListener {
            if (isConnected) {
                disconnect()
            } else {
                connectToServer()
            }
        }
    }

    /** Attempt to connect to the SnapSolve server. */
    private fun connectToServer() {
        val ip = ipAddressEditText.text.toString().trim()
        val port = portEditText.text.toString().toIntOrNull() ?: 8080

        if (ip.isEmpty()) {
            Toast.makeText(this, R.string.toast_enter_ip, Toast.LENGTH_SHORT).show()
            return
        }

        remoteControlClient.setServerConfig(ip, port)
        setStatusConnecting()

        lifecycleScope.launch {
            val success = withContext(Dispatchers.IO) { remoteControlClient.testConnection() }
            if (success) {
                // Notify the server to block the physical mouse.
                withContext(Dispatchers.IO) { remoteControlClient.connect() }
                saveAddress(ip, port)
                setConnected(true)
                Toast.makeText(
                    this@MainActivity,
                    getString(R.string.toast_connected, ip, port),
                    Toast.LENGTH_SHORT,
                ).show()
            } else {
                setConnected(false)
                Toast.makeText(this@MainActivity, R.string.toast_connect_failed, Toast.LENGTH_SHORT).show()
            }
        }
    }

    /** Disconnect from the server and reset UI state. */
    private fun disconnect() {
        // Notify the server to restore the physical mouse before resetting.
        lifecycleScope.launch {
            withContext(Dispatchers.IO) { remoteControlClient.disconnect() }
        }
        touchpadView.clearRemoteControlClient()
        // Re-attach a fresh client so reconnection works without restarting.
        remoteControlClient = RemoteControlClient()
        touchpadView.setRemoteControlClient(remoteControlClient)
        setConnected(false)
    }

    // -------------------------------------------------------------------------
    // Action buttons
    // -------------------------------------------------------------------------

    private fun setupActionButtons() {
        captureButton.setOnClickListener { executeAction("capture") }
        reselectButton.setOnClickListener { executeAction("reselect") }
        multiCaptureButton.setOnClickListener { executeAction("multi_capture") }
        endMultiButton.setOnClickListener { executeAction("end_multi_capture") }
        toggleStitchingButton.setOnClickListener { executeAction("toggle_stitching") }
        cycleSourceButton.setOnClickListener { executeAction("cycle_source") }
        togglePanelButton.setOnClickListener { executeAction("toggle_panel") }
        newChatButton.setOnClickListener { executeAction("new_chat_session") }
        cancelButton.setOnClickListener { executeAction("cancel") }
    }

    /**
     * Send a named action to the server.
     *
     * @param action Action identifier (e.g. `"capture"`, `"cancel"`).
     */
    private fun executeAction(action: String) {
        lifecycleScope.launch {
            val success = withContext(Dispatchers.IO) { remoteControlClient.executeAction(action) }
            if (!success) {
                Toast.makeText(
                    this@MainActivity,
                    getString(R.string.toast_action_error, action),
                    Toast.LENGTH_SHORT,
                ).show()
            }
        }
    }

    // -------------------------------------------------------------------------
    // UI state helpers
    // -------------------------------------------------------------------------

    /**
     * Update all UI elements to reflect the connected / disconnected state.
     *
     * @param connected `true` after a successful connection, `false` otherwise.
     */
    // The MotionEvent is part of the required onTouchEvent dispatch signature; the pointer
    // index is not needed here because we only decrement the global touchCount counter.
    private fun setConnected(connected: Boolean) {
        isConnected = connected

        connectButton.text = if (connected) getString(R.string.btn_disconnect) else getString(R.string.btn_connect)

        statusTextView.text = getString(if (connected) R.string.status_connected else R.string.status_disconnected)
        statusTextView.setTextColor(
            ContextCompat.getColor(
                this,
                if (connected) R.color.status_connected else R.color.status_disconnected,
            ),
        )

        val actionButtons = listOf(
            captureButton, reselectButton, multiCaptureButton, endMultiButton,
            toggleStitchingButton, cycleSourceButton, togglePanelButton,
            newChatButton, cancelButton,
        )
        actionButtons.forEach { it.isEnabled = connected }

        touchpadView.visibility = if (connected) View.VISIBLE else View.INVISIBLE
    }

    /** Show an intermediate "Connecting…" status while the network call is in flight. */
    private fun setStatusConnecting() {
        statusTextView.text = getString(R.string.status_connecting)
        statusTextView.setTextColor(ContextCompat.getColor(this, R.color.text_hint))
    }
}