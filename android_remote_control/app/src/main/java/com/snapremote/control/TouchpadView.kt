package com.snapsolve.remotecontrol

import android.content.Context
import android.graphics.Canvas
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.graphics.toColorInt
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job
import kotlin.math.absoluteValue

class TouchpadView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var remoteControlClient: RemoteControlClient? = null
    private val paint = Paint()

    // Touch tracking
    private var startX = 0f
    private var startY = 0f
    private var isDragging = false
    private var lastTouchTime = 0L
    private var touchCount = 0

    // Configuration
    private var sensitivity = 1.5f
    private var doubleClickTimeout = 300L // milliseconds

    // Long press for drag start
    private var longPressCheckJob: Job? = null
    private var isLongPress = false
    private var hasMoved = false

    init {
        paint.color = "#2C2C2C".toColorInt()
        paint.style = Paint.Style.FILL
    }

    fun setRemoteControlClient(client: RemoteControlClient) {
        this.remoteControlClient = client
    }

    fun setSensitivity(sensitivity: Float) {
        this.sensitivity = sensitivity
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)

        // Draw touch indicator
        if (isDragging) {
            paint.color = "#4CAF50".toColorInt()
            canvas.drawCircle(startX, startY, 20f, paint)
            paint.color = "#2C2C2C".toColorInt()
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        return when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> handleActionDown(event)
            MotionEvent.ACTION_POINTER_DOWN -> handleActionPointerDown()
            MotionEvent.ACTION_MOVE -> handleActionMove(event)
            MotionEvent.ACTION_UP -> handleActionUp()
            MotionEvent.ACTION_POINTER_UP -> handleActionPointerUp()
            MotionEvent.ACTION_CANCEL -> handleActionCancel()
            else -> super.onTouchEvent(event)
        }
    }

    private fun handleActionDown(event: MotionEvent): Boolean {
        startX = event.x
        startY = event.y
        isDragging = true
        touchCount = 1
        lastTouchTime = System.currentTimeMillis()
        hasMoved = false
        isLongPress = false
        // Cancel any existing long press check
        longPressCheckJob?.cancel()
        // Start a new long press check
        startLongPressCheck()
        invalidate()
        return true
    }

    private fun startLongPressCheck() {
        longPressCheckJob = CoroutineScope(Dispatchers.Main).launch {
            delay(500) // 500 milliseconds
            if (!hasMoved && isDragging && touchCount == 1) {
                isLongPress = true
                // Calculate relative coordinates
                val relativeX = (startX / width).coerceIn(0f, 1f)
                val relativeY = (startY / height).coerceIn(0f, 1f)
                remoteControlClient?.let { client ->
                    CoroutineScope(Dispatchers.IO).launch {
                        client.startDrag(relativeX, relativeY)
                    }
                }
            }
        }
    }

    private fun handleActionPointerDown(): Boolean {
        touchCount++
        if (touchCount == 2) {
            // Two-finger tap for right click
            handleRightClick()
        } else if (touchCount == 3) {
            // Three-finger tap for middle click
            handleMiddleClick()
        }
        return true
    }

    private fun handleActionMove(event: MotionEvent): Boolean {
        updateMoveState(event)
        sendMouseMoveIfDragging(event)
        return true
    }

    private fun updateMoveState(event: MotionEvent) {
        val dx = (event.x - startX).absoluteValue
        val dy = (event.y - startY).absoluteValue
        if (dx > 5f || dy > 5f) {
            hasMoved = true
        }
        if (hasMoved) {
            longPressCheckJob?.cancel()
            longPressCheckJob = null
        }
    }

    private fun sendMouseMoveIfDragging(event: MotionEvent) {
        if (!isDragging || touchCount != 1) return

        val relativeX = (event.x / width).coerceIn(0f, 1f)
        val relativeY = (event.y / height).coerceIn(0f, 1f)

        remoteControlClient?.let { client ->
            CoroutineScope(Dispatchers.IO).launch {
                client.moveMouse(relativeX, relativeY)
            }
        }

        startX = event.x
        startY = event.y
    }

    private fun handleActionUp(): Boolean {
        val timeDiff = System.currentTimeMillis() - lastTouchTime

        longPressCheckJob?.cancel()
        longPressCheckJob = null

        handleClickOnRelease(timeDiff)

        isDragging = false
        touchCount = 0
        isLongPress = false
        invalidate()
        return true
    }

    private fun handleClickOnRelease(timeDiff: Long) {
        if (touchCount != 1) return

        val clickType = if (timeDiff < doubleClickTimeout) "double" else "single"
        remoteControlClient?.let { client ->
            CoroutineScope(Dispatchers.IO).launch {
                if (clickType == "double") {
                    client.doubleClickMouse("left")
                } else {
                    client.clickMouse("left")
                }
            }
        }
    }

    private fun handleActionPointerUp(): Boolean {
        touchCount--
        return true
    }

    private fun handleActionCancel(): Boolean {
        // Cancel long press check
        longPressCheckJob?.cancel()
        longPressCheckJob = null
        isDragging = false
        touchCount = 0
        isLongPress = false
        invalidate()
        return true
    }

    private fun handleRightClick() {
        remoteControlClient?.let { client ->
            CoroutineScope(Dispatchers.IO).launch {
                client.clickMouse("right")
            }
        }
    }

    private fun handleMiddleClick() {
        remoteControlClient?.let { client ->
            CoroutineScope(Dispatchers.IO).launch {
                client.clickMouse("middle")
            }
        }
    }
}