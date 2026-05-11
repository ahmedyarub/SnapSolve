package com.snapsolve.remotecontrol

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {
    private lateinit var ipAddressEditText: EditText
    private lateinit var portEditText: EditText
    private lateinit var connectButton: Button
    private lateinit var remoteControlClient: RemoteControlClient

    // Action buttons
    private lateinit var captureButton: Button
    private lateinit var reselectButton: Button
    private lateinit var multiCaptureButton: Button
    private lateinit var endMultiButton: Button
    private lateinit var toggleStitchingButton: Button
    private lateinit var cycleSourceButton: Button
    private lateinit var togglePanelButton: Button
    private lateinit var newChatButton: Button
    private lateinit var cancelButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Initialize views
        ipAddressEditText = findViewById(R.id.ipAddressEditText)
        portEditText = findViewById(R.id.portEditText)
        connectButton = findViewById(R.id.connectButton)

        // Initialize action buttons
        captureButton = findViewById(R.id.captureButton)
        reselectButton = findViewById(R.id.reselectButton)
        multiCaptureButton = findViewById(R.id.multiCaptureButton)
        endMultiButton = findViewById(R.id.endMultiButton)
        toggleStitchingButton = findViewById(R.id.toggleStitchingButton)
        cycleSourceButton = findViewById(R.id.cycleSourceButton)
        togglePanelButton = findViewById(R.id.togglePanelButton)
        newChatButton = findViewById(R.id.newChatButton)
        cancelButton = findViewById(R.id.cancelButton)

        // Set default values
        ipAddressEditText.setText("192.168.1.100") // Default IP
        portEditText.setText("8080") // Default port

        // Initialize remote control client
        remoteControlClient = RemoteControlClient()

        // Set up connect button
        connectButton.setOnClickListener {
            connectToServer()
        }

        // Set up action buttons
        setupActionButtons()

        // Set up touchpad
        val touchpadView = findViewById<TouchpadView>(R.id.touchpadView)
        touchpadView.setRemoteControlClient(remoteControlClient)
    }

    private fun setupActionButtons() {
        captureButton.setOnClickListener {
            executeAction("capture")
        }

        reselectButton.setOnClickListener {
            executeAction("reselect")
        }

        multiCaptureButton.setOnClickListener {
            executeAction("multi_capture")
        }

        endMultiButton.setOnClickListener {
            executeAction("end_multi_capture")
        }

        toggleStitchingButton.setOnClickListener {
            executeAction("toggle_stitching")
        }

        cycleSourceButton.setOnClickListener {
            executeAction("cycle_source")
        }

        togglePanelButton.setOnClickListener {
            executeAction("toggle_panel")
        }

        newChatButton.setOnClickListener {
            executeAction("new_chat_session")
        }

        cancelButton.setOnClickListener {
            executeAction("cancel")
        }
    }

    private fun connectToServer() {
        val ipAddress = ipAddressEditText.text.toString()
        val port = portEditText.text.toString().toIntOrNull() ?: 8080

        if (ipAddress.isEmpty()) {
            Toast.makeText(this, "Please enter IP address", Toast.LENGTH_SHORT).show()
            return
        }

        // Update client configuration
        remoteControlClient.setServerConfig(ipAddress, port)

        // Test connection
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val success = remoteControlClient.testConnection()
                withContext(Dispatchers.Main) {
                    if (success) {
                        Toast.makeText(
                            this@MainActivity,
                            "Connected to $ipAddress:$port",
                            Toast.LENGTH_SHORT
                        ).show()
                        enableActionButtons(true)
                    } else {
                        Toast.makeText(
                            this@MainActivity,
                            "Failed to connect to server",
                            Toast.LENGTH_SHORT
                        ).show()
                        enableActionButtons(false)
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@MainActivity,
                        "Connection error: ${e.message}",
                        Toast.LENGTH_SHORT
                    ).show()
                    enableActionButtons(false)
                }
            }
        }
    }

    private fun executeAction(action: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val success = remoteControlClient.executeAction(action)
                withContext(Dispatchers.Main) {
                    if (success) {
                        Toast.makeText(
                            this@MainActivity,
                            "Action executed: $action",
                            Toast.LENGTH_SHORT
                        ).show()
                    } else {
                        Toast.makeText(
                            this@MainActivity,
                            "Failed to execute action: $action",
                            Toast.LENGTH_SHORT
                        ).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@MainActivity,
                        "Error: ${e.message}",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            }
        }
    }

    private fun enableActionButtons(enabled: Boolean) {
        captureButton.isEnabled = enabled
        reselectButton.isEnabled = enabled
        multiCaptureButton.isEnabled = enabled
        endMultiButton.isEnabled = enabled
        toggleStitchingButton.isEnabled = enabled
        cycleSourceButton.isEnabled = enabled
        togglePanelButton.isEnabled = enabled
        newChatButton.isEnabled = enabled
        cancelButton.isEnabled = enabled
    }
}