package dev.voicebrain.capture

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlin.concurrent.thread

/**
 * Transparent capture surface with a small visual feedback box (like the laptop overlay):
 * pulsing dot -> live waveform -> spinner (laptop thinks) -> checkmark -> done.
 * Launched by the assistant gesture (hold power), the QS tile, or the app.
 */
class CaptureActivity : Activity() {

    private var cancelled = false
    @Volatile private var discarded = false
    private lateinit var box: VisualBoxView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        box = VisualBoxView(this)
        val hint = TextView(this).apply {
            text = "tap = send · hold = cancel"
            textSize = 13f
            setTextColor(0xAA9B9B9B.toInt())
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            addView(box)
            addView(hint)
        }
        setContentView(FrameLayout(this).apply {
            addView(content, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        })

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                arrayOf(Manifest.permission.RECORD_AUDIO), 1)
            return // onRequestPermissionsResult retries
        }
        startCapture()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>,
                                            grantResults: IntArray) {
        if (requestCode == 1 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            startCapture()
        } else {
            Toast.makeText(this, "Microphone permission required", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    private fun startCapture() {
        box.setBoxState(VisualBoxView.BoxState.LISTENING)
        val recorder = Recorder()
        // tap the box = stop & send · hold the box = discard
        box.setOnClickListener { recorder.forceFinish() }
        box.setOnLongClickListener {
            discarded = true
            recorder.cancel()
            true
        }
        thread(name = "vb-capture") {
            val wav = recorder.record(this,
                onState = { state, level ->
                    runOnUiThread {
                        if (state == "recording") {
                            box.setBoxState(VisualBoxView.BoxState.RECORDING)
                            box.pushLevel(level)
                        } else {
                            box.setBoxState(VisualBoxView.BoxState.LISTENING)
                        }
                    }
                },
                isCancelled = { cancelled })

            if (cancelled || discarded) {
                runOnUiThread {
                    box.setBoxState(VisualBoxView.BoxState.ERR, "cancelled")
                    Toast.makeText(this, "Cancelled", Toast.LENGTH_SHORT).show()
                    box.postDelayed({ finish() }, 400)
                }
                return@thread
            }
            if (wav == null) {
                runOnUiThread {
                    Toast.makeText(this, "Nothing heard", Toast.LENGTH_SHORT).show()
                    finish()
                }
                return@thread
            }

            runOnUiThread { box.setBoxState(VisualBoxView.BoxState.WAITING) }
            val summary = try {
                val result = Uploader.upload(this, wav)
                runOnUiThread { box.setBoxState(VisualBoxView.BoxState.OK) }
                result
            } catch (e: Exception) {
                runOnUiThread { box.setBoxState(VisualBoxView.BoxState.ERR) }
                Uploader.saveOffline(this, wav)
            }
            runOnUiThread {
                Toast.makeText(this, summary, Toast.LENGTH_LONG).show()
                box.postDelayed({ finish() }, 600)
            }
        }
    }

    override fun onDestroy() {
        cancelled = true
        super.onDestroy()
    }
}
