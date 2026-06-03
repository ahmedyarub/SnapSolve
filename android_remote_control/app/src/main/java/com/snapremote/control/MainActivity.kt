package com.snapremote.control

import android.content.SharedPreferences
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.ArrayAdapter
import android.widget.AdapterView
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
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

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
 * ## Connection model
 * Uses a persistent WebSocket connection. UI state updates and response-image
 * notifications are **pushed** by the server via [RemoteControlListener] —
 * no polling loop is needed.
 *
 * ## Threading
 * All network calls are dispatched via [lifecycleScope] on [Dispatchers.IO] so they
 * are automatically canceled when the Activity is destroyed and never touch the UI
 * from a background thread. [RemoteControlListener] callbacks arrive on OkHttp's
 * background thread and are forwarded to the main thread via [runOnUiThread].
 */
class MainActivity : AppCompatActivity(), RemoteControlListener {

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
    private lateinit var typeTextButton: MaterialButton
    private lateinit var langSpinner: Spinner

    // Language codes matching the spinner entries (see strings.xml)
    private val langCodes = arrayOf(
        "", "en", "es", "fr", "de", "it", "pt", "ru", "zh",
        "ja", "ko", "ar", "hi", "tr", "pl", "nl", "sv",
        "cs", "ro", "hu", "uk", "el", "he", "th", "vi", "id", "ms",
    )

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    private lateinit var remoteControlClient: RemoteControlClient
    private lateinit var prefs: SharedPreferences

    /** Whether the client is currently connected to the server. */
    private var isConnected = false

    /** Suppress feedback loop when syncing the language spinner from a server push. */
    private var suppressLangSync = false

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getPreferences(MODE_PRIVATE)
        remoteControlClient = RemoteControlClient()
        remoteControlClient.setListener(this)

        bindViews()
        restoreSavedAddress()
        setupConnectButton()
        setupActionButtons()
        setupLanguageSpinner()
        setConnected(false) // Start in disconnected state
        attemptAutoConnect()
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isConnected) {
            remoteControlClient.disconnect()
        }
        remoteControlClient.setListener(null)
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
        typeTextButton = findViewById(R.id.typeTextButton)
        langSpinner = findViewById(R.id.langSpinner)

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

        // First verify the server is reachable via HTTP, then open WebSocket
        lifecycleScope.launch {
            val reachable = withContext(Dispatchers.IO) { remoteControlClient.testConnection() }
            if (reachable) {
                saveAddress(ip, port)
                // Open the persistent WebSocket connection.
                // onConnected() / onDisconnected() will be called via the listener.
                remoteControlClient.connect()
            } else {
                setConnected(false)
                Toast.makeText(this@MainActivity, R.string.toast_connect_failed, Toast.LENGTH_SHORT).show()
            }
        }
    }

    /** Disconnect from the server and reset UI state. */
    private fun disconnect() {
        remoteControlClient.disconnect()
        touchpadView.clearRemoteControlClient()

        // Re-attach a fresh client so reconnection works without restarting.
        remoteControlClient = RemoteControlClient()
        remoteControlClient.setListener(this)
        touchpadView.setRemoteControlClient(remoteControlClient)

        setConnected(false)
    }

    // -------------------------------------------------------------------------
    // RemoteControlListener — push-based callbacks from the server
    // -------------------------------------------------------------------------

    override fun onConnected() {
        runOnUiThread {
            setConnected(true)
            val ip = ipAddressEditText.text.toString().trim()
            val port = portEditText.text.toString().toIntOrNull() ?: 8080
            Toast.makeText(
                this,
                getString(R.string.toast_connected, ip, port),
                Toast.LENGTH_SHORT,
            ).show()
        }
    }

    override fun onDisconnected(reason: String) {
        runOnUiThread {
            if (isConnected) {
                // Unexpected disconnection — reset UI
                setConnected(false)
                Toast.makeText(this, "Disconnected: $reason", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onStateUpdate(buttons: JSONObject?, hasNewResponseImage: Boolean, transcriptionLanguage: String?) {
        runOnUiThread {
            if (buttons != null) {
                updateButtonStates(buttons)
            }
            if (transcriptionLanguage != null) {
                syncLanguageSpinner(transcriptionLanguage)
            }
        }
        if (hasNewResponseImage) {
            handleNewResponseImage()
        }
    }

    override fun onError(message: String) {
        runOnUiThread {
            Toast.makeText(this, "Server error: $message", Toast.LENGTH_SHORT).show()
        }
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
        typeTextButton.setOnClickListener { showTypeTextDialog() }
    }

    /**
     * Send a named action to the server via WebSocket.
     *
     * @param action Action identifier (e.g. `"capture"`, `"cancel"`).
     */
    private fun executeAction(action: String) {
        val success = remoteControlClient.executeAction(action)
        if (!success) {
            Toast.makeText(
                this,
                getString(R.string.toast_action_error, action),
                Toast.LENGTH_SHORT,
            ).show()
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
            newChatButton, cancelButton, typeTextButton,
        )
        actionButtons.forEach { it.isEnabled = connected }
        langSpinner.isEnabled = connected

        touchpadView.visibility = if (connected) View.VISIBLE else View.INVISIBLE
    }

    /**
     * Apply button visibility/enabled states received from the server.
     */
    private fun updateButtonStates(buttonsObj: JSONObject) {
        fun updateBtn(btn: View, name: String) {
            val btnState = buttonsObj.optJSONObject(name)
            if (btnState != null) {
                btn.visibility = if (btnState.optBoolean("visible", true)) View.VISIBLE else View.GONE
                btn.isEnabled = btnState.optBoolean("enabled", true)
            }
        }

        updateBtn(captureButton, "capture")
        updateBtn(reselectButton, "reselect")
        updateBtn(multiCaptureButton, "multi")
        updateBtn(endMultiButton, "end_multi")
        updateBtn(toggleStitchingButton, "stitching")
        updateBtn(cycleSourceButton, "cycle")
        updateBtn(cancelButton, "cancel")
        // newChatButton and togglePanelButton are kept always visible.
    }

    /**
     * Fetch the response image via HTTP, display it, and acknowledge receipt
     * via WebSocket.
     */
    private fun handleNewResponseImage() {
        lifecycleScope.launch {
            val imageBytes = withContext(Dispatchers.IO) { remoteControlClient.fetchResponseImage() }
            if (imageBytes != null) {
                try {
                    // Save to cache dir
                    val imageFile = File(cacheDir, "response_image.png")
                    withContext(Dispatchers.IO) {
                        FileOutputStream(imageFile).use { fos ->
                            fos.write(imageBytes)
                        }
                    }

                    // Ack receipt via WebSocket
                    remoteControlClient.ackResponseImage()

                    // View image
                    val intent = Intent(this@MainActivity, ImageViewerActivity::class.java).apply {
                        putExtra("EXTRA_IMAGE_PATH", imageFile.absolutePath)
                    }
                    startActivity(intent)

                } catch (e: Exception) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Failed to view response image", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }

    /** Show an intermediate "Connecting…" status while the network call is in flight. */
    private fun setStatusConnecting() {
        statusTextView.text = getString(R.string.status_connecting)
        statusTextView.setTextColor(ContextCompat.getColor(this, R.color.text_hint))
    }

    // -------------------------------------------------------------------------
    // Language spinner
    // -------------------------------------------------------------------------

    private fun setupLanguageSpinner() {
        val adapter = ArrayAdapter.createFromResource(
            this,
            R.array.transcription_languages,
            android.R.layout.simple_spinner_item,
        )
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        langSpinner.adapter = adapter
        // Default to English (index 1 — 0 is Auto-detect)
        langSpinner.setSelection(1)

        langSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, pos: Int, id: Long) {
                if (suppressLangSync) {
                    suppressLangSync = false
                    return
                }
                if (isConnected && pos in langCodes.indices) {
                    remoteControlClient.setTranscriptionLanguage(langCodes[pos])
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    /**
     * Sync the spinner to match the language pushed by the server,
     * without re-sending the value back.
     */
    private fun syncLanguageSpinner(langCode: String) {
        val idx = langCodes.indexOf(langCode)
        if (idx >= 0 && idx != langSpinner.selectedItemPosition) {
            suppressLangSync = true
            langSpinner.setSelection(idx)
        }
    }

    private fun showTypeTextDialog() {
        val container = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(48, 24, 48, 24)
        }

        val editText = EditText(this).apply {
            hint = "Enter text to type..."
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 3
            gravity = android.view.Gravity.TOP or android.view.Gravity.START
        }
        container.addView(editText)

        val sendButton = android.widget.Button(this).apply {
            text = "Send"
            setOnClickListener {
                val text = editText.text.toString()
                if (text.isNotEmpty()) {
                    editText.text.clear()
                    val success = remoteControlClient.typeText(text)
                    if (!success) {
                        Toast.makeText(this@MainActivity, "Failed to send text", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
        val params = android.widget.LinearLayout.LayoutParams(
            android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
            android.widget.LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            topMargin = 16
        }
        container.addView(sendButton, params)

        val dialog = androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Type Text")
            .setView(container)
            .setNegativeButton("Close", null)
            .create()

        dialog.setOnShowListener {
            editText.requestFocus()
            val imm = getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
            imm.showSoftInput(editText, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
        }

        dialog.show()
    }
}