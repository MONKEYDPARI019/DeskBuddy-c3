package com.deskbuddy.app

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper

/** Finds DeskBuddy on the local network through its mDNS service _deskbuddy._tcp. */
class Discovery(context: Context) {
    private val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val main = Handler(Looper.getMainLooper())
    private var listener: NsdManager.DiscoveryListener? = null

    /**
     * [nameHint]: only accept services whose name contains this (e.g. "c3" picks
     * DeskBuddy C3 "deskbuddy-c3" and ignores a DeskBuddy v2 "deskbuddy" on the same WiFi).
     */
    fun find(onFound: (String, Int) -> Unit, nameHint: String? = null, onFail: (String) -> Unit) {
        stop()
        val l = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {}
            override fun onDiscoveryStopped(serviceType: String) {}
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                main.post { onFail("search failed ($errorCode)") }
            }
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onServiceLost(service: NsdServiceInfo) {}
            override fun onServiceFound(service: NsdServiceInfo) {
                if (nameHint != null && !service.serviceName.contains(nameHint, ignoreCase = true)) return
                @Suppress("DEPRECATION")
                nsd.resolveService(service, object : NsdManager.ResolveListener {
                    override fun onResolveFailed(s: NsdServiceInfo, errorCode: Int) {}
                    override fun onServiceResolved(s: NsdServiceInfo) {
                        @Suppress("DEPRECATION")
                        val ip = s.host?.hostAddress ?: return
                        main.post { onFound(ip, s.port) }
                        stop()
                    }
                })
            }
        }
        listener = l
        nsd.discoverServices("_deskbuddy._tcp", NsdManager.PROTOCOL_DNS_SD, l)
        // give up after 10 s so the UI doesn't wait forever
        main.postDelayed({ if (listener === l) { stop(); onFail("not found - type the IP instead") } }, 10_000)
    }

    fun stop() {
        val l = listener ?: return
        listener = null
        try { nsd.stopServiceDiscovery(l) } catch (_: Exception) {}
    }
}
