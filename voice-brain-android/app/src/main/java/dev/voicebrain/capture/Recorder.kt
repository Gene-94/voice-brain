package dev.voicebrain.capture

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.File
import java.io.FileOutputStream
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Hands-free recorder for a think-while-talking workflow:
 *  - armed: waits (patiently) for the first above-floor energy — humming counts —
 *           while learning the ambient noise floor so background noise never
 *           false-starts a capture
 *  - recording: records THROUGH every pause and hum — there is NO silence
 *           auto-stop. Only tap-to-send, hold-to-cancel, or the 3-min safety cap
 *           end a recording. You think as long as you want.
 * Writes a real 16 kHz mono PCM WAV to cacheDir.
 */
class Recorder(
    private val vadRms: Double = 0.02,
    private val armTimeoutFrames: Int = 2250, // 45s to start talking — generous think time
    private val maxRecordingFrames: Int = 9000, // 3-min safety cap
) {
    /** Tap-to-send: finish recording now and send what was said. */
    @Volatile private var forceDone = false
    fun forceFinish() { forceDone = true }

    /** Hold-to-cancel: discard and close. */
    @Volatile private var userCancelled = false
    fun cancel() { userCancelled = true }

    companion object {
        const val SAMPLE_RATE = 16000
        const val FRAME_MS = 20
        const val FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS / 1000 // 320
        const val CALIBRATION_FRAMES = 12 // ~0.24s ambient calibration before the gate arms
    }

    // ---- noise-adaptive start gate: steady background noise becomes the floor,
    //      only energy ABOVE it can begin a recording.
    private var noiseFloor = -1.0
    private fun effectiveThreshold(): Double {
        if (noiseFloor < 0) return vadRms
        return max(vadRms, noiseFloor * 1.6 + 0.003)
    }
    private fun learnFloor(rms: Double) {
        noiseFloor = if (noiseFloor < 0) rms else 0.9 * noiseFloor + 0.1 * rms
    }

    /** Blocking. Returns the recorded WAV, or null if nothing was said / cancelled. */
    @SuppressLint("MissingPermission") // callers check RECORD_AUDIO first
    fun record(context: Context, onState: (String, Double) -> Unit, isCancelled: () -> Boolean): File? {
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(MediaRecorder.AudioSource.MIC, SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBuf, FRAME_SAMPLES * 4))
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            return null
        }

        val frame = ShortArray(FRAME_SAMPLES)
        val buffer = ArrayList<ShortArray>(1024)
        var recording = false
        var loudStreak = 0
        var armedFrames = 0
        var recordedFrames = 0

        try {
            record.startRecording()
            onState("armed", 0.0)
            while (!isCancelled() && !userCancelled) {
                if (forceDone) {
                    if (!recording) return null   // tapped before saying anything
                    break                          // tapped mid-thought: send what we have
                }
                val n = record.read(frame, 0, FRAME_SAMPLES)
                if (n <= 0) break

                var acc = 0.0
                for (i in 0 until n) acc += frame[i].toDouble() * frame[i]
                val rms = sqrt(acc / n) / 32768.0
                val threshold = effectiveThreshold()
                val loud = rms >= threshold
                if (!loud) learnFloor(rms)

                if (!recording) {
                    // Calibration window: the first ~0.25s only learns the noise
                    // floor — ambient noise can never trigger an instant start.
                    if (armedFrames < CALIBRATION_FRAMES) {
                        learnFloor(rms)
                        armedFrames++
                        continue
                    }
                }

                if (!recording) {
                    if (loud) {
                        loudStreak++
                        if (loudStreak >= 3) { // ~60ms of above-floor energy -> start
                            recording = true
                            buffer.add(frame.copyOf())
                            onState("recording", rms)
                        }
                    } else {
                        loudStreak = 0
                        armedFrames++
                        if (armedFrames > armTimeoutFrames) return null
                    }
                } else {
                    buffer.add(frame.copyOf())
                    recordedFrames++
                    onState("recording", rms)
                    // NOTE: intentionally NO silence auto-stop — the user taps to send.
                    if (recordedFrames >= maxRecordingFrames) break
                }
            }
        } finally {
            record.stop()
            record.release()
        }

        if (userCancelled) return null
        if (!recording || buffer.isEmpty()) return null
        return writeWav(context, buffer)
    }

    private fun writeWav(context: Context, frames: List<ShortArray>): File {
        val samples = frames.sumOf { it.size }
        val out = File(context.cacheDir, "vb-${System.currentTimeMillis()}.wav")
        FileOutputStream(out).use { fos ->
            val header = ByteArray(44)
            val totalLen = samples * 2
            header[0] = 'R'.code.toByte(); header[1] = 'I'.code.toByte()
            header[2] = 'F'.code.toByte(); header[3] = 'F'.code.toByte()
            writeInt(header, 4, 36 + totalLen)
            header[8] = 'W'.code.toByte(); header[9] = 'A'.code.toByte()
            header[10] = 'V'.code.toByte(); header[11] = 'E'.code.toByte()
            header[12] = 'f'.code.toByte(); header[13] = 'm'.code.toByte()
            header[14] = 't'.code.toByte(); header[15] = ' '.code.toByte()
            writeInt(header, 16, 16)
            writeShort(header, 20, 1)          // PCM
            writeShort(header, 22, 1)          // mono
            writeInt(header, 24, SAMPLE_RATE)
            writeInt(header, 28, SAMPLE_RATE * 2) // byte rate
            writeShort(header, 32, 2)         // block align
            writeShort(header, 34, 16)        // bits per sample
            header[36] = 'd'.code.toByte(); header[37] = 'a'.code.toByte()
            header[38] = 't'.code.toByte(); header[39] = 'a'.code.toByte()
            writeInt(header, 40, totalLen)
            fos.write(header)
            val bytes = ByteArray(8192)
            var idx = 0
            for (frame in frames) {
                for (s in frame) {
                    bytes[idx++] = (s.toInt() and 0xFF).toByte()
                    bytes[idx++] = ((s.toInt() shr 8) and 0xFF).toByte()
                    if (idx == bytes.size) {
                        fos.write(bytes); idx = 0
                    }
                }
            }
            if (idx > 0) fos.write(bytes, 0, idx)
        }
        return out
    }

    private fun writeInt(b: ByteArray, off: Int, v: Int) {
        b[off] = (v and 0xFF).toByte()
        b[off + 1] = ((v shr 8) and 0xFF).toByte()
        b[off + 2] = ((v shr 16) and 0xFF).toByte()
        b[off + 3] = ((v shr 24) and 0xFF).toByte()
    }

    private fun writeShort(b: ByteArray, off: Int, v: Int) {
        b[off] = (v and 0xFF).toByte()
        b[off + 1] = ((v shr 8) and 0xFF).toByte()
    }
}
