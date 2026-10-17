package dev.voicebrain.capture

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.os.SystemClock
import android.view.View
import kotlin.math.max
import kotlin.math.sin

/**
 * Visual feedback box — Obsidian dark mode:
 *   LISTENING -> pulsing purple ring ("listening…" label)
 *   RECORDING -> live purple waveform + elapsed m:ss ("tap to send")
 *   WAITING   -> purple spinner ("thinking…")
 *   OK        -> green check ("saved")
 *   ERR       -> red ✗ (custom label, e.g. "cancelled")
 * 150dp card: #1E1E1E, 1px #3A3A3A border, rounded 22dp — matches the vault.
 */
class VisualBoxView(context: Context) : View(context) {

    enum class BoxState { LISTENING, RECORDING, WAITING, OK, ERR }

    private var state = BoxState.LISTENING
    private var stateLabel = ""
    private val levels = ArrayDeque<Float>()

    // Obsidian palette
    private val cBg = 0xF21E1E1E.toInt()
    private val cBorder = 0xFF3A3A3A.toInt()
    private val cAccent = 0xFF8B6DF1.toInt()
    private val cAccentDim = 0x668B6DF1.toInt()
    private val cText = 0xFFDADADA.toInt()
    private val cMuted = 0xFF9B9B9B.toInt()
    private val cOk = 0xFF4ADE80.toInt()
    private val cErr = 0xFFF26D6D.toInt()

    private val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = cBg
        style = Paint.Style.FILL
    }
    private val border = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = cBorder
        style = Paint.Style.STROKE
        strokeWidth = 2f
    }
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = cMuted
        textSize = 11f * resources.displayMetrics.density
        textAlign = Paint.Align.CENTER
    }

    private var recordingSince = 0L

    fun setBoxState(s: BoxState, label: String? = null) {
        state = s
        stateLabel = label ?: defaultLabel(s)
        if (s == BoxState.RECORDING) {
            if (recordingSince == 0L) recordingSince = SystemClock.elapsedRealtime()
        } else {
            recordingSince = 0L
            levels.clear()
        }
        postInvalidateOnAnimation()
    }

    private fun defaultLabel(s: BoxState): String = when (s) {
        BoxState.LISTENING -> "listening…"
        BoxState.RECORDING -> "tap to send"
        BoxState.WAITING -> "thinking…"
        BoxState.OK -> "saved"
        BoxState.ERR -> "error"
    }

    fun pushLevel(v: Double) {
        levels.addLast(v.toFloat().coerceIn(0f, 1f))
        while (levels.size > WAVE_BARS) levels.removeFirst()
        postInvalidateOnAnimation()
    }

    override fun onMeasure(widthSpec: Int, heightSpec: Int) {
        val dp = resources.displayMetrics.density
        setMeasuredDimension((160 * dp).toInt(), (160 * dp).toInt())
    }

    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        val card = RectF(0f, 0f, w, h)
        canvas.drawRoundRect(card, 22f, 22f, bg)
        canvas.drawRoundRect(card, 22f, 22f, border)

        val cx = w / 2
        val t = SystemClock.elapsedRealtime() / 1000.0

        when (state) {
            BoxState.LISTENING -> {
                val pulse = (0.5 + 0.5 * sin(t * 3.0)).toFloat()
                stroke.color = cAccent
                stroke.strokeWidth = 4f
                stroke.alpha = (100 + 120 * pulse).toInt()
                val rad = h * (0.19f + 0.05f * pulse)
                canvas.drawCircle(cx, h * 0.44f, rad, stroke)
                stroke.style = Paint.Style.FILL
                stroke.alpha = 255
                canvas.drawCircle(cx, h * 0.44f, 3.5f, stroke)
                stroke.style = Paint.Style.STROKE
                postInvalidateOnAnimation()
            }
            BoxState.RECORDING -> {
                // elapsed time
                val secs = ((SystemClock.elapsedRealtime() - recordingSince) / 1000).toInt()
                text.color = cText
                canvas.drawText("${secs / 60}:${String.format("%02d", secs % 60)}", cx, h * 0.20f, text)
                // purple waveform
                stroke.color = cAccent
                stroke.strokeWidth = w / 30f
                val barW = w / (WAVE_BARS * 1.6f)
                var x = (w - (WAVE_BARS * barW * 1.6f - barW * 0.6f)) / 2
                for (i in 0 until WAVE_BARS) {
                    val lvl = if (i < levels.size) levels.elementAt(i) else 0.02f
                    val bh = max(4f, lvl * h * 0.5f)
                    canvas.drawLine(x, h * 0.44f - bh / 2, x, h * 0.44f + bh / 2, stroke)
                    x += barW * 1.6f
                }
                postInvalidateOnAnimation()
            }
            BoxState.WAITING -> {
                stroke.color = cAccent
                stroke.strokeWidth = 6.5f
                val rad = h * 0.20f
                val a0 = (t * 5.0).toFloat()
                canvas.drawArc(cx - rad, h * 0.44f - rad, cx + rad, h * 0.44f + rad,
                    (a0 * 180 / Math.PI.toFloat()), 225f, false, stroke)
                postInvalidateOnAnimation()
            }
            BoxState.OK -> {
                stroke.color = cOk
                stroke.strokeWidth = 9f
                val r2 = h * 0.17f
                val cyc = h * 0.44f
                canvas.drawLine(cx - r2, cyc + r2 * 0.1f, cx - r2 * 0.25f, cyc + r2 * 0.8f, stroke)
                canvas.drawLine(cx - r2 * 0.25f, cyc + r2 * 0.8f, cx + r2 * 1.05f, cyc - r2 * 0.85f, stroke)
            }
            BoxState.ERR -> {
                stroke.color = cErr
                stroke.strokeWidth = 8f
                val r2 = h * 0.17f
                val cyc = h * 0.44f
                canvas.drawLine(cx - r2, cyc - r2, cx + r2, cyc + r2, stroke)
                canvas.drawLine(cx + r2, cyc - r2, cx - r2, cyc + r2, stroke)
            }
        }

        // state label pinned near the bottom of the card
        text.color = cMuted
        canvas.drawText(stateLabel, cx, h * 0.87f, text)
    }

    companion object {
        const val WAVE_BARS = 16
    }
}
