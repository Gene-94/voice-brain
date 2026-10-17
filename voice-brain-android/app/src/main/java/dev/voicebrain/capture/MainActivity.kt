package dev.voicebrain.capture

import android.app.Activity
import android.app.AlertDialog
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import kotlin.concurrent.thread

/**
 * Setup screen with a guided flow:
 *   1. Scan for laptop  (auto-discovers on the LAN)
 *   2. Pair with laptop (enter the 6-digit PIN shown by `voice-brain pair` on the laptop)
 *   3. Test connection
 * Manual/advanced settings live at the bottom for edge cases.
 */
class MainActivity : Activity() {

    private lateinit var status: TextView
    private lateinit var pairButton: Button
    private lateinit var testButton: Button
    private lateinit var progress: ProgressBar
    private lateinit var server: EditText
    private lateinit var token: EditText
    private lateinit var syncthing: EditText

    private var selectedHost: DiscoveryClient.Host? = null
    private val dp: Float by lazy { resources.displayMetrics.density }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val dp = resources.displayMetrics.density
        val pad = (18 * dp).toInt()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        val scroll = ScrollView(this).apply { addView(root) }

        // ---- header
        root.addView(TextView(this).apply {
            text = "🎙️ Voice Brain Capture"
            textSize = 22f
            setTextColor(resources.getColor(R.color.ob_text_bright))
            setPadding(0, 0, 0, (4 * dp).toInt())
        })
        root.addView(TextView(this).apply {
            text = "Talk to your Obsidian vault from anywhere. Everything runs on your laptop — the phone just records."
            textSize = 13f
            setTextColor(resources.getColor(R.color.ob_muted))
            setPadding(0, 0, 0, (16 * dp).toInt())
        })

        // ---- status card
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.card)
            setPadding(pad, (12 * dp).toInt(), pad, (12 * dp).toInt())
        }
        status = TextView(this).apply {
            textSize = 15f
            setTextColor(resources.getColor(R.color.ob_text))
        }
        card.addView(status)
        progress = ProgressBar(this).apply {
            visibility = View.GONE
            isIndeterminate = true
        }
        card.addView(progress)
        root.addView(card)
        root.addView(Space((16 * dp).toInt()))

        // ---- primary flow buttons (Obsidian purple)
        val scan = Button(this).apply {
            text = "①  Scan for laptop"
            stylePrimary()
        }
        pairButton = Button(this).apply {
            text = "②  Pair with laptop"
            isEnabled = false
            stylePrimary()
        }
        testButton = Button(this).apply {
            text = "③  Test connection"
            stylePrimary()
        }
        root.addView(scan)
        root.addView(pairButton)
        root.addView(testButton)
        root.addView(Space((12 * dp).toInt()))

        // ---- advanced section
        root.addView(TextView(this).apply {
            text = "Advanced (manual — normally not needed)"
            textSize = 12f
            setTextColor(resources.getColor(R.color.ob_muted))
            setPadding(0, (12 * dp).toInt(), 0, (4 * dp).toInt())
        })
        server = EditText(this).apply {
            hint = getString(R.string.hint_server)
            setText(Prefs.serverUrl(this@MainActivity))
            styleField()
        }
        token = EditText(this).apply {
            hint = getString(R.string.hint_token)
            setText(Prefs.token(this@MainActivity))
            inputType = InputType.TYPE_CLASS_TEXT
            styleField()
        }
        syncthing = EditText(this).apply {
            hint = getString(R.string.hint_syncthing)
            setText(Prefs.syncthingFolder(this@MainActivity))
            styleField()
        }
        val save = Button(this).apply {
            text = getString(R.string.save)
            styleSecondary()
        }
        root.addView(server)
        root.addView(token)
        root.addView(syncthing)
        root.addView(save)

        setContentView(scroll)
        refreshStatus()

        // ---------------------------------------------------------------- actions

        scan.setOnClickListener { doScan() }
        pairButton.setOnClickListener { doPair() }
        testButton.setOnClickListener { doTest() }
        save.setOnClickListener {
            persist()
            Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show()
            refreshStatus()
        }
    }

    // A vertical spacer helper (LinearLayout params inside vertical root)
    private fun Space(heightPx: Int): View =
        View(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, heightPx)
        }

    private fun Button.stylePrimary() {
        setBackgroundResource(R.drawable.btn_primary)
        setTextColor(0xFFFFFFFF.toInt())
        textSize = 16f
        stateListAnimator = null
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = (8 * dp).toInt() }
    }

    private fun Button.styleSecondary() {
        setBackgroundResource(R.drawable.btn_secondary)
        setTextColor(resources.getColor(R.color.ob_text))
        stateListAnimator = null
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = (8 * dp).toInt() }
    }

    private fun EditText.styleField() {
        setTextColor(resources.getColor(R.color.ob_text))
        setHintTextColor(resources.getColor(R.color.ob_muted))
        backgroundTintList = android.content.res.ColorStateList.valueOf(
            resources.getColor(R.color.ob_border))
        setPadding((12 * dp).toInt(), (12 * dp).toInt(), (12 * dp).toInt(), (12 * dp).toInt())
    }

    private fun refreshStatus() {
        val host = Prefs.serverUrl(this)
        val hasToken = Prefs.token(this).isNotEmpty()
        val lines = when {
            host.isEmpty() -> "Not set up yet.\nStart with ① Scan for laptop."
            hasToken -> "Laptop: ${host.removePrefix("http://").substringBefore('/')}  ·  token saved ✓"
            else -> "Laptop found, but no token yet.\nRun 'voice-brain pair' on the laptop, then tap ②"
        }
        status.text = lines
        pairButton.isEnabled = host.isNotEmpty()
    }

    private fun showProgress(show: Boolean) {
        progress.visibility = if (show) View.VISIBLE else View.GONE
    }

    private fun doScan() {
        showProgress(true)
        status.text = "Scanning your network…"
        thread {
            val hosts = try {
                DiscoveryClient.scan()
            } catch (e: Exception) {
                emptyList()
            }
            runOnUiThread {
                showProgress(false)
                when {
                    hosts.isEmpty() -> {
                        status.text = "No Voice Brain laptop found.\n" +
                            "Is the daemon running? (systemctl --user status voice-brain)"
                    }
                    hosts.size == 1 -> selectHost(hosts[0])
                    else -> {
                        val names = hosts.map { it.toString() }.toTypedArray()
                        AlertDialog.Builder(this)
                            .setTitle("Found Voice Brain on:")
                            .setItems(names) { _, which -> selectHost(hosts[which]) }
                            .setNegativeButton("Cancel", null)
                            .show()
                    }
                }
            }
        }
    }

    private fun selectHost(host: DiscoveryClient.Host) {
        selectedHost = host
        server.setText(host.captureUrl)
        persist()
        refreshStatus()
        val hasToken = Prefs.token(this).isNotEmpty()
        Toast.makeText(this, "Found ${host.name} (${host.ip})" +
                if (hasToken) " — test it (③)" else " — now run 'voice-brain pair' on the laptop, then ②",
            Toast.LENGTH_LONG).show()
    }

    private fun doPair() {
        val host = selectedHost ?: run {
            // derive from a manual URL if the user typed one
            val url = Prefs.serverUrl(this)
            val m = Regex("http://([\\d.]+):(\\d+)").find(url) ?: run {
                Toast.makeText(this, "Scan first (①), or set the URL in Advanced",
                    Toast.LENGTH_SHORT).show()
                return
            }
            DiscoveryClient.Host("laptop", m.groupValues[1], m.groupValues[2].toInt())
        }
        val input = EditText(this).apply {
            hint = "6-digit PIN from the laptop"
            inputType = InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(android.text.InputFilter.LengthFilter(6))
            gravity = Gravity.CENTER
            textSize = 22f
        }
        AlertDialog.Builder(this)
            .setTitle("Pair with ${host.name}")
            .setMessage("Run this on your laptop first:\n\n    voice-brain pair\n\nThen enter the PIN it shows:")
            .setView(input)
            .setPositiveButton("Pair") { _, _ ->
                val pin = input.text.toString().trim()
                if (pin.length != 6) {
                    Toast.makeText(this, "PIN must be 6 digits", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                showProgress(true)
                status.text = "Pairing with ${host.name}…"
                thread {
                    try {
                        val tokenValue = PairingClient.pair(
                            host.ip, host.port, pin, Build.MODEL ?: "phone")
                        runOnUiThread {
                            server.setText(host.captureUrl)
                            this.token.setText(tokenValue)
                            persist()
                            showProgress(false)
                            status.text = "Paired with ${host.name} (${host.ip}) ✓"
                            Toast.makeText(this, "Paired! Try ③ Test connection", Toast.LENGTH_LONG).show()
                        }
                    } catch (e: Exception) {
                        runOnUiThread {
                            showProgress(false)
                            status.text = "Pairing failed: ${e.message}"
                        }
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun doTest() {
        persist()
        showProgress(true)
        status.text = "Testing connection…"
        thread {
            val result = Uploader.test(this)
            runOnUiThread {
                showProgress(false)
                refreshStatus()
                status.text = result
                Toast.makeText(this, result, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun persist() {
        Prefs.save(this, server.text.toString(), token.text.toString(),
            syncthing.text.toString())
    }
}
