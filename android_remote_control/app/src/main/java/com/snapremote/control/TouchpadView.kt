package com.snapsolve.remotecontrol

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import androidx.core.graphics.toColorInt

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
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                startX = event.x
                startY = event.y
                isDragging = true
                touchCount = 1
                lastTouchTime = System.currentTimeMillis()
                invalidate()
                return true
            }

            MotionEvent.ACTION_POINTER_DOWN -> {
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

            MotionEvent.ACTION_MOVE -> {
                if (isDragging && touchCount == 1) {
                    val dx = (event.x - startX) * sensitivity
                    val dy = (event.y - startY) * sensitivity

                    // Convert to relative coordinates (0-1)
                    val relativeX = (event.x / width).coerceIn(0f, 1f)
                    val relativeY = (event.y / height).coerceIn(0f, 1f)

                    // Send mouse move
                    remoteControlClient?.let { client ->
                        CoroutineScope(Dispatchers.IO).launch {
                            client.moveMouse(relativeX, relativeY)
                        }
                    }

                    startX = event.x
                    startY = event.y
                }
                return true
            }

            MotionEvent.ACTION_UP -> {
                val currentTime = System.currentTimeMillis()
                val timeDiff = currentTime - lastTouchTime

                if (touchCount == 1 && timeDiff < doubleClickTimeout) {
                    // Double click detected
                    handleDoubleClick()
                } else if (touchCount == 1) {
                    // Single click
                    handleClick()
                }

                isDragging = false
                touchCount = 0
                invalidate()
                return true
            }

            MotionEvent.ACTION_POINTER_UP -> {
                touchCount--
                return true
            }

            MotionEvent.ACTION_CANCEL -> {
                isDragging = false
                touchCount = 0
                invalidate()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun handleClick() {
        remoteControlClient?.let { client ->
            CoroutineScope(Dispatchers.IO).launch {
                client.clickMouse("left")
            }
        }
    }

    private fun handleDoubleClick() {
        remoteControlClient?.let { client ->
            CoroutineScope(Dispatchers.IO).launch {
                client.doubleClickMouse("left")
            }
        }
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

    // Long press for drag start - TODO: Implement properly
    // private var longPressRunnable: Runnable? = null
    // private var isLongPress = false

    // override fun onLongPress() {
    //     isLongPress = true
    //     val relativeX = (startX / width).coerceIn(0f, 1f)
    //     val relativeY = (startY / height).coerceIn(0f, 1f)

    //     remoteControlClient?.let { client ->
    //         CoroutineScope(Dispatchers.IO).launch {
    //             client.startDrag(relativeX, relativeY)
    //         }
    //     }
    // }
}