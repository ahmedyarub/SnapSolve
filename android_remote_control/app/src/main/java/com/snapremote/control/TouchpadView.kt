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
     * Whether a long-press was detected for the current touch sequence, meaning the
     * subsequent ACTION_UP should send a drag-end instead of a click.
     */
    private var isLongPress = false

    /** Coroutine job that fires after [LONG_PRESS_TIMEOUT_MS] to begin a drag. */
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
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Attach the network client. Call this once the user has connected to the server.
     *
     * @param client Configured [RemoteControlClient] instance.
     */
    fun setRemoteControlClient(client: RemoteControlClient) {
        remoteControlClient = client
    }

    /**
     * Detach the network client when the user disconnects.
     * Pending gestures will be silently discarded.
     */
    fun clearRemoteControlClient() {
        remoteControlClient = null
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
        longPressJob = startLongPressTimer(event.x, event.y)
        invalidate()
        return true
    }

    // — Additional finger touches down —
    private fun handlePointerDown(event: MotionEvent): Boolean {
        touchCount++
        longPressJob?.cancel() // Long-press only applies to single-finger

        when (touchCount) {
            2 -> {
                // Record Y for two-finger scroll detection
                scrollStartY = event.getY(0)
                scrollAccumulator = 0f
            }

            3 -> dispatchIO { it.clickMouse("middle") }
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
        }

        if (hasMoved && !isLongPress) {
            val now = System.currentTimeMillis()
            if (now - lastMoveSentMs >= MOUSE_MOVE_INTERVAL_MS) {
                lastMoveSentMs = now
                // Send relative delta to server for a true touchpad feel
                val relX = (event.x / width).coerceIn(0f, 1f)
                val relY = (event.y / height).coerceIn(0f, 1f)
                dispatchIO { it.moveMouse(relX, relY) }
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
            dispatchIO { it.scrollMouse(ticks) }
        }
    }

    // — Last finger lifts —
    private fun handleUp(): Boolean {
        longPressJob?.cancel()
        longPressJob = null

        val now = System.currentTimeMillis()

        if (touchCount == 1) {
            when {
                isLongPress -> {
                    // End the drag at the current position
                    val relX = (lastX / width).coerceIn(0f, 1f)
                    val relY = (lastY / height).coerceIn(0f, 1f)
                    dispatchIO { it.endDrag(relX, relY) }
                }

                !hasMoved -> {
                    // Tap: determine single vs double click
                    if (now - lastUpTimeMs <= DOUBLE_CLICK_TIMEOUT_MS) {
                        dispatchIO { it.doubleClickMouse("left") }
                        lastUpTimeMs = 0L // reset so a triple tap won't re-trigger
                    } else {
                        dispatchIO { it.clickMouse("left") }
                        lastUpTimeMs = now
                    }
                }
                // If moved without long-press: cursor was already moved, nothing extra to do.
            }
        }

        if (touchCount == 2 && !hasMoved) {
            // Two-finger lift without scroll movement = right click
            dispatchIO { it.clickMouse("right") }
        }

        isPointerDown = false
        touchCount = 0
        isLongPress = false
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
        isPointerDown = false
        touchCount = 0
        isLongPress = false
        invalidate()
        return true
    }

    // -------------------------------------------------------------------------
    // Long-press timer
    // -------------------------------------------------------------------------

    /**
     * Start a coroutine that fires after [LONG_PRESS_TIMEOUT_MS] and begins a drag
     * if the finger has not moved in the meantime.
     */
    private fun startLongPressTimer(x: Float, y: Float): Job? {
        val owner = findViewTreeLifecycleOwner() ?: return null
        return owner.lifecycleScope.launch(Dispatchers.Main) {
            delay(LONG_PRESS_TIMEOUT_MS)
            if (!hasMoved && isPointerDown && touchCount == 1) {
                isLongPress = true
                invalidate()
                val relX = (x / width).coerceIn(0f, 1f)
                val relY = (y / height).coerceIn(0f, 1f)
                dispatchIO { it.startDrag(relX, relY) }
            }
        }
    }

    // -------------------------------------------------------------------------
    // Dispatch helper
    // -------------------------------------------------------------------------

    /**
     * Run a network call on the IO dispatcher, bound to the Activity lifecycle
     * so the coroutine is canceled automatically when the Activity is destroyed.
     *
     * @param block Lambda receiving the current [RemoteControlClient]. Skipped silently
     *              if no client is attached.
     */
    private fun dispatchIO(block: suspend (RemoteControlClient) -> Unit) {
        val client = remoteControlClient ?: return
        val owner = findViewTreeLifecycleOwner() ?: return
        owner.lifecycleScope.launch(Dispatchers.IO) {
            block(client)
        }
    }
}