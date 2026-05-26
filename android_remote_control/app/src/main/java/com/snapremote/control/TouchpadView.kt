package com.snapremote.control

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.content.ContextCompat
import androidx.lifecycle.findViewTreeLifecycleOwner
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.absoluteValue
import kotlinx.coroutines.channels.Channel

/**
 * A full-screen touchpad view that translates finger gestures into remote mouse commands.
 *
 * ## Supported gestures
 * | Gesture                   | Mouse action          |
 * |---------------------------|-----------------------|
 * | Single finger move        | Move cursor           |
 * | Single tap (quick lift)   | Left click            |
 * | Double tap                | Left double-click     |
 * | Two-finger tap            | Right click           |
 * | Three-finger tap          | Middle click          |
 * | Two-finger vertical swipe | Scroll wheel          |
 * | Long press (≥500 ms)      | Begin drag (mouseDown)|
 * | Lift after long press     | End drag (mouseUp)    |
 *
 * ## Thread safety
 * Touch events arrive on the main thread. Network requests are dispatched on
 * [Dispatchers.IO] using the host Activity's [lifecycleScope] so that all
 * coroutines are automatically canceled when the Activity is destroyed.
 */
class TouchpadView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {

    // -------------------------------------------------------------------------
    // Dependencies
    // -------------------------------------------------------------------------

    /** Set by the owning Activity once a server connection has been established. */
    private var remoteControlClient: RemoteControlClient? = null

    // -------------------------------------------------------------------------
    // Paint
    // -------------------------------------------------------------------------

    private val backgroundPaint: Paint = Paint().apply {
        color = ContextCompat.getColor(context, R.color.surface_dark)
        style = Paint.Style.FILL
    }

    private val dragIndicatorPaint: Paint = Paint().apply {
        color = ContextCompat.getColor(context, R.color.touchpad_drag_indicator)
        style = Paint.Style.FILL
    }

    // -------------------------------------------------------------------------
    // Touch tracking state
    // -------------------------------------------------------------------------

    /** X coordinate of the initial touch-down (updated as the finger moves). */
    private var lastX = 0f

    /** Y coordinate of the initial touch-down (updated as the finger moves). */
    private var lastY = 0f

    /** Whether at least one pointer is currently pressing down. */
    private var isPointerDown = false

    /** Number of pointers currently touching the screen. */
    private var touchCount = 0

    /**
     * Timestamp (ms) of the most recent ACTION_UP. Used to detect double-taps:
     * a second tap within [DOUBLE_CLICK_TIMEOUT_MS] of this value is a double click.
     */
    private var lastUpTimeMs = 0L

    /**
     * Whether the current touch has moved far enough to be considered a swipe/drag
     * rather than a tap.
     */
    private var hasMoved = false

    /**
     * Whether a long-press was detected for the current touch sequence, meaning a
     * right click has been triggered and the subsequent ACTION_UP should be ignored.
     */
    private var isLongPress = false

    /** Whether the finger is in a potential drag state (tap followed by tap down within timeout). */
    private var isPotentialDrag = false

    /** Whether we are currently in an active drag operation. */
    private var isDragging = false

    /** Coroutine job that fires after [LONG_PRESS_TIMEOUT_MS] to trigger right click. */
    private var longPressJob: Job? = null

    // -------------------------------------------------------------------------
    // Scroll state (two-finger swipe)
    // -------------------------------------------------------------------------

    /** Y position of pointer 0 when the second finger first touched down. */
    private var scrollStartY = 0f

    /** Accumulated Y delta since the last scroll event was sent. */
    private var scrollAccumulator = 0f

    // -------------------------------------------------------------------------
    // Mouse-move throttle
    // -------------------------------------------------------------------------

    /** Timestamp of the last mouse-move network call (ms). */
    private var lastMoveSentMs = 0L

    // -------------------------------------------------------------------------
    // Mouse event queue
    // -------------------------------------------------------------------------

    private val eventQueue = java.util.LinkedList<MouseEvent>()
    private val signalChannel = Channel<Unit>(Channel.CONFLATED)
    private var moveJob: Job? = null
    private var clickJob: Job? = null

    // -------------------------------------------------------------------------
    // Configuration constants
    // -------------------------------------------------------------------------

    /** Minimum pixels a finger must travel before a touch is treated as a move. */
    private val moveThresholdPx = 8f

    /** Sensitivity multiplier for mouse movement (can be exposed as a setting). */
    private var sensitivity = 1.5f

    /** Two taps within this window (ms) are interpreted as a double click. */
    private val DOUBLE_CLICK_TIMEOUT_MS = 300L

    /** A finger held down for this long without movement starts a drag. */
    private val LONG_PRESS_TIMEOUT_MS = 500L

    /** Minimum interval between successive mouse-move HTTP calls (ms). Caps at ~30 Hz. */
    private val MOUSE_MOVE_INTERVAL_MS = 33L

    /** Accumulated scroll pixels needed to trigger one scroll-wheel click. */
    private val SCROLL_PIXELS_PER_TICK = 40f

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        startMoveJob()
    }

    override fun onDetachedFromWindow() {
        stopMoveJob()
        super.onDetachedFromWindow()
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Attach the network client. Call this once the user has connected to the server.
     *
     * @param client Configured [RemoteControlClient] instance.
     */
    fun setRemoteControlClient(client: RemoteControlClient) {
        remoteControlClient = client
        startMoveJob()
    }

    /**
     * Detach the network client when the user disconnects.
     * Pending gestures will be silently discarded.
     */
    fun clearRemoteControlClient() {
        remoteControlClient = null
        stopMoveJob()
        clickJob?.cancel()
        clickJob = null
        synchronized(eventQueue) {
            eventQueue.clear()
        }
    }

    /**
     * Adjust the cursor movement sensitivity.
     *
     * @param value Multiplier applied to raw pixel deltas. Default: 1.5.
     */
    fun setSensitivity(value: Float) {
        sensitivity = value
    }

    // -------------------------------------------------------------------------
    // Drawing
    // -------------------------------------------------------------------------

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), backgroundPaint)

        // Show a green circle at the touch point while a drag is active.
        if (isLongPress && isPointerDown) {
            canvas.drawCircle(lastX, lastY, 24f, dragIndicatorPaint)
        }
    }

    // -------------------------------------------------------------------------
    // Touch handling
    // -------------------------------------------------------------------------

    override fun onTouchEvent(event: MotionEvent): Boolean {
        return when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> handleDown(event)
            MotionEvent.ACTION_POINTER_DOWN -> handlePointerDown(event)
            MotionEvent.ACTION_MOVE -> handleMove(event)
            MotionEvent.ACTION_UP -> handleUp()
            MotionEvent.ACTION_POINTER_UP -> handlePointerUp(event)
            MotionEvent.ACTION_CANCEL -> handleCancel()
            else -> super.onTouchEvent(event)
        }
    }

    // — First finger touches down —
    private fun handleDown(event: MotionEvent): Boolean {
        lastX = event.x
        lastY = event.y
        scrollStartY = event.y
        scrollAccumulator = 0f
        isPointerDown = true
        touchCount = 1
        hasMoved = false
        isLongPress = false
        longPressJob?.cancel()

        val now = System.currentTimeMillis()
        isPotentialDrag = (lastUpTimeMs > 0L && now - lastUpTimeMs <= DOUBLE_CLICK_TIMEOUT_MS)

        // Cancel the delayed click job since we have a second touch down (double tap or drag)
        clickJob?.cancel()
        clickJob = null

        if (!isPotentialDrag) {
            longPressJob = startLongPressTimer()
        }

        invalidate()
        return true
    }

    // — Additional finger touches down —
    private fun handlePointerDown(event: MotionEvent): Boolean {
        touchCount++
        longPressJob?.cancel() // Long-press only applies to single-finger
        clickJob?.cancel()
        clickJob = null
        isPotentialDrag = false

        when (touchCount) {
            2 -> {
                // Record Y for two-finger scroll detection
                scrollStartY = event.getY(0)
                scrollAccumulator = 0f
            }

            3 -> enqueueMouseEvent(MouseEvent.Click("middle"))
        }
        return true
    }

    // — Finger(s) move —
    private fun handleMove(event: MotionEvent): Boolean {
        if (touchCount == 2) {
            handleScrollMove(event)
            return true
        }

        if (touchCount != 1) return true

        val dx = event.x - lastX
        val dy = event.y - lastY

        if (!hasMoved && (dx.absoluteValue > moveThresholdPx || dy.absoluteValue > moveThresholdPx)) {
            hasMoved = true
            longPressJob?.cancel()
            longPressJob = null

            // Double-tap drag: if in potential drag state and finger moves, begin the drag.
            if (isPotentialDrag && !isDragging) {
                val relX = (event.x / width).coerceIn(0f, 1f)
                val relY = (event.y / height).coerceIn(0f, 1f)
                enqueueMouseEvent(MouseEvent.DragStart(relX, relY))
                isDragging = true
                isPotentialDrag = false
            }
        }

        if (hasMoved && !isLongPress) {
            val now = System.currentTimeMillis()
            if (now - lastMoveSentMs >= MOUSE_MOVE_INTERVAL_MS) {
                lastMoveSentMs = now
                // Send relative delta to server for a true touchpad feel
                val relX = (event.x / width).coerceIn(0f, 1f)
                val relY = (event.y / height).coerceIn(0f, 1f)
                enqueueMouseEvent(MouseEvent.Move(relX, relY))
            }
        }

        lastX = event.x
        lastY = event.y
        return true
    }

    // Handle vertical two-finger swipe as scroll.
    private fun handleScrollMove(event: MotionEvent) {
        val currentY = event.getY(0)
        val deltaY = scrollStartY - currentY // positive = moving up = scroll up
        scrollStartY = currentY
        scrollAccumulator += deltaY

        val ticks = (scrollAccumulator / SCROLL_PIXELS_PER_TICK).toInt()
        if (ticks != 0) {
            scrollAccumulator -= ticks * SCROLL_PIXELS_PER_TICK
            enqueueMouseEvent(MouseEvent.Scroll(ticks))
        }
    }

    // — Last finger lifts —
    private fun handleUp(): Boolean {
        longPressJob?.cancel()
        longPressJob = null

        val now = System.currentTimeMillis()

        if (touchCount == 1) {
            when {
                isDragging -> {
                    // End the drag at the current position
                    val relX = (lastX / width).coerceIn(0f, 1f)
                    val relY = (lastY / height).coerceIn(0f, 1f)
                    enqueueMouseEvent(MouseEvent.DragEnd(relX, relY))
                    isDragging = false
                }

                isLongPress -> {
                    // Long press right click already sent, nothing to do on release
                    isLongPress = false
                }

                !hasMoved -> {
                    // Tap: determine single vs double click
                    if (isPotentialDrag) {
                        enqueueMouseEvent(MouseEvent.DoubleClick("left"))
                        lastUpTimeMs = 0L // reset so a triple tap won't re-trigger
                        isPotentialDrag = false
                    } else {
                        // Delay single left click to see if it is part of double tap
                        val owner = findViewTreeLifecycleOwner()
                        if (owner != null) {
                            lastUpTimeMs = now
                            clickJob = owner.lifecycleScope.launch(Dispatchers.Main) {
                                delay(DOUBLE_CLICK_TIMEOUT_MS)
                                enqueueMouseEvent(MouseEvent.Click("left"))
                                lastUpTimeMs = 0L
                            }
                        } else {
                            enqueueMouseEvent(MouseEvent.Click("left"))
                            lastUpTimeMs = now
                        }
                    }
                }
            }
        }

        if (touchCount == 2 && !hasMoved) {
            // Two-finger lift without scroll movement = right click
            clickJob?.cancel()
            clickJob = null
            enqueueMouseEvent(MouseEvent.Click("right"))
        }

        isPointerDown = false
        touchCount = 0
        isLongPress = false
        isPotentialDrag = false
        invalidate()
        return true
    }

    // — Additional finger lifts (multitouch) —
    // The MotionEvent is part of the required onTouchEvent dispatch signature; the pointer
    // index is not needed here because we only decrement the global touchCount counter.
    private fun handlePointerUp(@Suppress("UNUSED_PARAMETER") event: MotionEvent): Boolean {
        if (touchCount > 0) touchCount--
        return true
    }

    // — Touch canceled by system —
    private fun handleCancel(): Boolean {
        longPressJob?.cancel()
        longPressJob = null
        clickJob?.cancel()
        clickJob = null
        isPointerDown = false
        touchCount = 0
        isLongPress = false
        isPotentialDrag = false
        isDragging = false
        invalidate()
        return true
    }

    // -------------------------------------------------------------------------
    // Long-press timer
    // -------------------------------------------------------------------------

    /**
     * Start a coroutine that fires after [LONG_PRESS_TIMEOUT_MS] and triggers a right click
     * if the finger has not moved in the meantime.
     */
    private fun startLongPressTimer(): Job? {
        val owner = findViewTreeLifecycleOwner() ?: return null
        return owner.lifecycleScope.launch(Dispatchers.Main) {
            delay(LONG_PRESS_TIMEOUT_MS)
            if (!hasMoved && isPointerDown && touchCount == 1) {
                isLongPress = true
                performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
                invalidate()
                enqueueMouseEvent(MouseEvent.Click("right"))
            }
        }
    }

    // -------------------------------------------------------------------------
    // Event processing loop
    // -------------------------------------------------------------------------

    private fun enqueueMouseEvent(event: MouseEvent) {
        synchronized(eventQueue) {
            if (event is MouseEvent.Move && eventQueue.isNotEmpty()) {
                val last = eventQueue.last
                if (last is MouseEvent.Move) {
                    eventQueue.removeLast()
                }
            }
            eventQueue.add(event)
        }
        signalChannel.trySend(Unit)
    }

    private fun startMoveJob() {
        val client = remoteControlClient ?: return
        val owner = findViewTreeLifecycleOwner() ?: return
        moveJob?.cancel()
        moveJob = owner.lifecycleScope.launch(Dispatchers.IO) {
            for (signal in signalChannel) {
                while (true) {
                    val nextEvent = synchronized(eventQueue) {
                        if (eventQueue.isNotEmpty()) eventQueue.removeFirst() else null
                    } ?: break

                    if (remoteControlClient != client) break

                    executeMouseEvent(client, nextEvent)
                }
            }
        }
    }

    private fun stopMoveJob() {
        moveJob?.cancel()
        moveJob = null
    }

    private fun executeMouseEvent(client: RemoteControlClient, event: MouseEvent) {
        when (event) {
            is MouseEvent.Move -> client.moveMouse(event.x, event.y)
            is MouseEvent.Click -> client.clickMouse(event.button)
            is MouseEvent.DoubleClick -> client.doubleClickMouse(event.button)
            is MouseEvent.DragStart -> client.startDrag(event.x, event.y)
            is MouseEvent.DragEnd -> client.endDrag(event.x, event.y)
            is MouseEvent.Scroll -> client.scrollMouse(event.delta)
        }
    }

    private sealed class MouseEvent {
        data class Move(val x: Float, val y: Float) : MouseEvent()
        data class Click(val button: String) : MouseEvent()
        data class DoubleClick(val button: String) : MouseEvent()
        data class DragStart(val x: Float, val y: Float) : MouseEvent()
        data class DragEnd(val x: Float, val y: Float) : MouseEvent()
        data class Scroll(val delta: Int) : MouseEvent()
    }
}