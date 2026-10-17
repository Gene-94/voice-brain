package dev.voicebrain.capture

import android.content.Context
import android.net.wifi.WifiManager
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * Laptop discovery — no hardcoded IPs.
 *
 * Strategy (broadcast often gets filtered, so we belt-and-braces):
 *   1. UDP broadcast "VB_DISCOVER" to 255.255.255.255 and the subnet broadcast
 *   2. Parallel UDP unicast sweep of the whole /24 subnet (254 hosts, ~64 threads)
 * The laptop's responder answers with {"service":"voice-brain","name":...,"port":...}
 */
object DiscoveryClient {

    data class Host(val name: String, val ip: String, val port: Int) {
        val captureUrl: String get() = "http://$ip:$port/api/capture"
        override fun toString(): String = "$name  ($ip)"
    }

    private const val TAG = "VB-Discovery"

    fun scan(timeoutMs: Long = 5000): List<Host> {
        val found = ConcurrentHashMap<String, Host>()
        android.util.Log.d(TAG, "scan: prefix=${localPrefix()}")

        // ---- phase 1: broadcasts
        val udpTargets = mutableListOf("255.255.255.255")
        subnetBroadcastAddress()?.let { udpTargets.add(it) }
        for (target in udpTargets) {
            try {
                DatagramSocket().use { sock ->
                    sock.broadcast = true
                    sock.soTimeout = 700
                    val packet = DatagramPacket("VB_DISCOVER".toByteArray(), 11,
                        InetAddress.getByName(target), 47798)
                    sock.send(packet)
                    val buf = ByteArray(512)
                    val resp = DatagramPacket(buf, buf.size)
                    try {
                        sock.receive(resp)
                        parseHost(String(resp.data, 0, resp.length),
                            resp.address.hostAddress)?.let { found[it.ip] = it }
                    } catch (_: java.net.SocketTimeoutException) {
                    }
                }
            } catch (_: Exception) {
            }
        }

        // ---- phase 2: /24 unicast sweep
        val prefix = localPrefix() ?: return found.values.sortedBy { it.ip }
        val latch = CountDownLatch(254)
        val perHostTimeoutMs = 600 // generous: phone WiFi power-save adds latency
        for (i in 1..254) {
            val ip = "$prefix$i"
            thread(start = true) {
                try {
                    DatagramSocket().use { sock ->
                        sock.soTimeout = perHostTimeoutMs
                        val packet = DatagramPacket("VB_DISCOVER".toByteArray(), 11,
                            InetAddress.getByName(ip), 47798)
                        sock.send(packet)
                        val buf = ByteArray(512)
                        val resp = DatagramPacket(buf, buf.size)
                        try {
                            sock.receive(resp)
                            parseHost(String(resp.data, 0, resp.length),
                                resp.address.hostAddress)?.let { found[it.ip] = it }
                        } catch (_: java.net.SocketTimeoutException) {
                        }
                    }
                } catch (_: Exception) {
                } finally {
                    latch.countDown()
                }
            }
        }
        latch.await(timeoutMs, TimeUnit.MILLISECONDS)
        android.util.Log.d(TAG, "scan done: ${found.size} host(s): ${found.keys.joinToString()}")
        return found.values.sortedBy { it.ip }
    }

    /** Extract the phone's WiFi /24 prefix, e.g. "192.168.31.".
     *  CRITICAL: prefer wlan/eth interfaces — cellular rmnet* often enumerates first
     *  and would make us sweep the carrier network instead of the LAN. */
    private fun localPrefix(): String? {
        return try {
            val wifiPrefixes = mutableListOf<String>()
            val otherPrefixes = mutableListOf<String>()
            val en = java.net.NetworkInterface.getNetworkInterfaces() ?: return null
            for (nif in en) {
                if (!nif.isUp || nif.isLoopback) continue
                val name = nif.name.lowercase()
                val isCellular = name.startsWith("rmnet") || name.startsWith("ccmni") ||
                    name.startsWith("v4") || name.startsWith("v6")
                val isVirtual = name.startsWith("usb") || name.startsWith("dummy") ||
                    name.startsWith("ap") || name == "lo"
                if (isCellular || isVirtual) continue
                for (addr in nif.inetAddresses) {
                    if (addr.isLoopbackAddress) continue
                    val s = addr.hostAddress ?: continue
                    if (s.contains(':')) continue // IPv4 only
                    val parts = s.split(".")
                    if (parts.size != 4) continue
                    val prefix = parts.subList(0, 3).joinToString(".") + "."
                    val isWifi = name.startsWith("wlan") || name.startsWith("swlan") ||
                        name.startsWith("eth")
                    if (isWifi) wifiPrefixes.add(prefix) else otherPrefixes.add(prefix)
                }
            }
            (wifiPrefixes + otherPrefixes).firstOrNull()
        } catch (_: Exception) {
            null
        }
    }

    private fun subnetBroadcastAddress(): String? {
        val prefix = localPrefix() ?: return null
        return prefix + "255"
    }

    private fun parseHost(json: String, ip: String?): Host? {
        return try {
            val name = Regex("\"name\"\\s*:\\s*\"([^\"]+)\"").find(json)?.groupValues?.get(1) ?: "laptop"
            val port = Regex("\"port\"\\s*:\\s*(\\d+)").find(json)?.groupValues?.get(1)?.toInt() ?: 47799
            if (!json.contains("voice-brain")) return null
            Host(name, ip ?: "unknown", port)
        } catch (_: Exception) {
            null
        }
    }
}
