package dev.voicebrain.capture

import android.content.Context

/** App settings (SharedPreferences — no framework magic). */
object Prefs {
    private const val FILE = "voice_brain"

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun serverUrl(ctx: Context): String =
        prefs(ctx).getString("server_url", "") ?: ""

    fun token(ctx: Context): String =
        prefs(ctx).getString("token", "") ?: ""

    fun syncthingFolder(ctx: Context): String =
        prefs(ctx).getString("syncthing_folder", "") ?: ""

    fun save(ctx: Context, serverUrl: String, token: String, syncthingFolder: String) {
        prefs(ctx).edit()
            .putString("server_url", serverUrl.trim().trimEnd('/'))
            .putString("token", token.trim())
            .putString("syncthing_folder", syncthingFolder.trim())
            .apply()
    }
}
