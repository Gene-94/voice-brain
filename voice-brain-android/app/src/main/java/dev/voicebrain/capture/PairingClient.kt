package dev.voicebrain.capture

import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/** LocalSend-style pairing: PIN in, token out. No typing of secrets. */
object PairingClient {

    /** Blocking. Returns the auth token, or throws with a human-readable message. */
    fun pair(hostIp: String, port: Int, pin: String, deviceName: String): String {
        val url = "http://$hostIp:$port/pair"
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 5000
            readTimeout = 15000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
        }
        try {
            OutputStreamWriter(conn.outputStream).use { os ->
                os.write(JSONObject().put("pin", pin.trim()).put("name", deviceName).toString())
                os.flush()
            }
            val code = conn.responseCode
            val body = if (code in 200..299) conn.inputStream.bufferedReader().readText()
            else conn.errorStream?.bufferedReader()?.readText() ?: "HTTP $code"
            if (code != 200) {
                val msg = try {
                    JSONObject(body).optString("error", "HTTP $code")
                } catch (_: Exception) {
                    "HTTP $code"
                }
                throw java.io.IOException(msg)
            }
            val doc = JSONObject(body)
            if (!doc.optBoolean("ok", false)) {
                throw java.io.IOException(doc.optString("error", "pairing failed"))
            }
            return doc.getString("token")
        } finally {
            conn.disconnect()
        }
    }
}
