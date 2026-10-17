package dev.voicebrain.capture

import android.content.Context
import java.io.File
import java.io.FileInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.file.Files
import java.nio.file.Paths
import java.nio.file.StandardCopyOption

/** Uploads the WAV to the Obsidian plugin's capture server (raw bytes + headers). */
object Uploader {

    class Unreachable(cause: Exception) : Exception(cause)

    /** Blocking. Returns the server's result summary. */
    fun upload(context: Context, wav: File): String {
        val url = Prefs.serverUrl(context)
        if (url.isEmpty()) throw IllegalStateException("No server URL configured — open the app once.")
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 8000
            readTimeout = 300000 // whisper + gemma4:12b can take a while
            doOutput = true
            setRequestProperty("Content-Type", "audio/wav")
            setRequestProperty("X-VB-Filename", wav.name)
            Prefs.token(context).takeIf { it.isNotEmpty() }?.let {
                setRequestProperty("X-VB-Token", it)
            }
        }
        try {
            conn.outputStream.use { os -> FileInputStream(wav).use { it.copyTo(os) } }
            val code = conn.responseCode
            val body = if (code in 200..299) conn.inputStream.bufferedReader().readText()
            else "HTTP $code"
            if (code != 200) throw java.io.IOException("server said $code: $body")
            // server returns {"ok":true,"summary":"💜 2 dreams saved\n..."}
            val summary = Regex("\"summary\"\\s*:\\s*\"(.*?)(?<!\\\\)\"")
                .find(body)?.groupValues?.get(1)
                ?.replace("\\n", "\n")?.replace("\\\"", "\"") ?: body
            return summary
        } catch (e: Exception) {
            throw Unreachable(e)
        } finally {
            conn.disconnect()
            wav.delete()
        }
    }

    /** Offline path: drop the recording into a Syncthing folder the plugin ingests. */
    fun saveOffline(context: Context, wav: File): String {
        val folder = Prefs.syncthingFolder(context)
        if (folder.isEmpty()) {
            wav.delete()
            return "offline and no Syncthing folder set — recording lost. " +
                   "Configure one to make offline captures survive."
        }
        val dir = File(folder).apply { mkdirs() }
        val dest = File(dir, "vb-${System.currentTimeMillis()}.wav")
        try {
            Files.move(wav.toPath(), dest.toPath(), StandardCopyOption.REPLACE_EXISTING)
            return "offline — saved to ${dest.name} (will sync when the laptop is back)"
        } catch (e: Exception) {
            return "offline save failed: ${e.message}"
        } finally {
            wav.delete()
        }
    }

    /** Connectivity + token check used by the settings screen.
     *  /health proves the laptop is reachable; /whoami proves the token is valid. */
    fun test(context: Context): String {
        val base = Prefs.serverUrl(context).removeSuffix("/api/capture")
        val token = Prefs.token(context)
        // 1. reachability
        try {
            val conn = URL("$base/health").openConnection() as HttpURLConnection
            conn.connectTimeout = 4000
            conn.readTimeout = 4000
            val reachable = conn.responseCode == 200
            val code = conn.responseCode
            conn.disconnect()
            if (!reachable) return "unreachable (HTTP $code)"
        } catch (e: Exception) {
            return "unreachable: ${e.message}"
        }
        // 2. token validity
        if (token.isEmpty()) return "reachable, but NO TOKEN — pair with the laptop (②)"
        return try {
            val conn = URL("$base/whoami").openConnection() as HttpURLConnection
            conn.connectTimeout = 4000
            conn.readTimeout = 4000
            conn.setRequestProperty("X-VB-Token", token)
            val ok = conn.responseCode == 200
            val body = if (ok) conn.inputStream.bufferedReader().readText() else ""
            conn.disconnect()
            if (ok) "OK — paired with ${Regex("\"name\"\\s*:\\s*\"([^\"]+)\"").find(body)?.groupValues?.get(1) ?: "laptop"} ✓"
            else "laptop reachable, but token REJECTED — re-pair with the laptop (②)"
        } catch (e: Exception) {
            "reachable, but token check failed: ${e.message}"
        }
    }
}
