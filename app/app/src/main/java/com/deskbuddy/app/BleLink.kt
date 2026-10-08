package com.deskbuddy.app

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.ArrayDeque
import java.util.UUID

/**
 * Bluetooth LE link to DeskBuddy C3 (Nordic UART Service).
 *
 *   RX 6E400002  the app writes JSON lines to the device
 *   TX 6E400003  the device notifies JSON lines to the app
 *
 * Every message is one JSON object + '\n', cut into (MTU - 3)-byte pieces.
 * Scans for the service, connects, raises the MTU, enables notifications,
 * then reports "connected". Reconnects with backoff while started.
 * Permissions (BLUETOOTH_SCAN / BLUETOOTH_CONNECT, or location before Android 12)
 * are requested by MainActivity before this is used.
 */
@SuppressLint("MissingPermission")
class BleLink(
    private val context: Context,
    private val onStatus: (connected: Boolean, text: String) -> Unit,
    private val onLine: (String) -> Unit,
) {
    companion object {
        val SERVICE: UUID = UUID.fromString("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        val RX: UUID = UUID.fromString("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
        val TX: UUID = UUID.fromString("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        private const val SCAN_TIMEOUT_MS = 15_000L
    }

    private val handler = Handler(Looper.getMainLooper())
    private val adapter get() = (context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter

    @Volatile private var wanted = false
    @Volatile private var gatt: BluetoothGatt? = null
    @Volatile private var rx: BluetoothGattCharacteristic? = null
    @Volatile var ready = false
        private set
    private var scanning = false
    private var mtu = 23
    private var backoffMs = 2000L

    private val writeQueue = ArrayDeque<ByteArray>()
    private var writing = false
    private val incoming = StringBuilder()

    // ------------------------------------------------------------------ public

    @Synchronized
    fun start() {
        if (wanted) return
        wanted = true
        backoffMs = 2000L
        scan()
    }

    @Synchronized
    fun stop() {
        wanted = false
        handler.removeCallbacksAndMessages(null)
        stopScan()
        closeGatt()
        onStatus(false, "disconnected")
    }

    /** Queue one JSON message. Returns false if not connected. */
    fun sendLine(json: String): Boolean {
        val g = gatt ?: return false
        if (!ready) return false
        val bytes = (json + "\n").toByteArray(Charsets.UTF_8)
        val chunk = (mtu - 3).coerceAtLeast(20)
        synchronized(writeQueue) {
            var i = 0
            while (i < bytes.size) {
                val end = (i + chunk).coerceAtMost(bytes.size)
                writeQueue.add(bytes.copyOfRange(i, end))
                i = end
            }
        }
        pumpWrites(g)
        return true
    }

    // ------------------------------------------------------------------ scan

    private fun scan() {
        if (!wanted) return
        val a = adapter
        if (a == null || !a.isEnabled) {
            onStatus(false, "Bluetooth is off, retrying in ${backoffMs / 1000}s")
            retryLater()
            return
        }
        val scanner = a.bluetoothLeScanner ?: run { retryLater(); return }
        onStatus(false, "searching for DeskBuddy C3 (Bluetooth)...")
        val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(SERVICE)).build()
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        scanning = true
        scanner.startScan(listOf(filter), settings, scanCallback)
        handler.postDelayed({
            if (scanning) {
                stopScan()
                onStatus(false, "DeskBuddy C3 not found, retrying in ${backoffMs / 1000}s")
                retryLater()
            }
        }, SCAN_TIMEOUT_MS)
    }

    private fun stopScan() {
        if (!scanning) return
        scanning = false
        try { adapter?.bluetoothLeScanner?.stopScan(scanCallback) } catch (_: Exception) {}
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            if (!scanning) return
            stopScan()
            handler.post { connect(result.device) }
        }

        override fun onScanFailed(errorCode: Int) {
            scanning = false
            onStatus(false, "Bluetooth scan failed ($errorCode)")
            retryLater()
        }
    }

    private fun retryLater() {
        if (!wanted) return
        handler.postDelayed({ synchronized(this) { if (wanted && gatt == null) scan() } }, backoffMs)
        backoffMs = (backoffMs * 2).coerceAtMost(30_000L)
    }

    // ------------------------------------------------------------------ GATT

    private fun connect(device: BluetoothDevice) {
        if (!wanted) return
        onStatus(false, "connecting to ${device.address}...")
        gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
    }

    private fun closeGatt() {
        ready = false
        rx = null
        synchronized(writeQueue) { writeQueue.clear(); writing = false }
        incoming.setLength(0)
        gatt?.let { try { it.disconnect(); it.close() } catch (_: Exception) {} }
        gatt = null
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) {
                mtu = 23
                if (!g.requestMtu(247)) g.discoverServices()
            } else {
                val was = ready
                handler.post {
                    synchronized(this@BleLink) {
                        if (gatt === g || gatt == null) closeGatt() else try { g.close() } catch (_: Exception) {}
                        onStatus(false, if (was) "connection lost, searching again..." else "could not connect, retrying...")
                        if (wanted) { backoffMs = 2000L; retryLater() }
                    }
                }
            }
        }

        override fun onMtuChanged(g: BluetoothGatt, newMtu: Int, status: Int) {
            if (status == BluetoothGatt.GATT_SUCCESS) mtu = newMtu
            g.discoverServices()
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            val svc = g.getService(SERVICE)
            val tx = svc?.getCharacteristic(TX)
            rx = svc?.getCharacteristic(RX)
            if (tx == null || rx == null) {
                onStatus(false, "not a DeskBuddy C3")
                g.disconnect()
                return
            }
            g.setCharacteristicNotification(tx, true)
            val cccd = tx.getDescriptor(CCCD)
            if (Build.VERSION.SDK_INT >= 33) {
                g.writeDescriptor(cccd, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
            } else {
                @Suppress("DEPRECATION")
                cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                @Suppress("DEPRECATION")
                g.writeDescriptor(cccd)
            }
        }

        override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) {
            if (d.uuid == CCCD && status == BluetoothGatt.GATT_SUCCESS) {
                ready = true
                backoffMs = 2000L
                onStatus(true, "connected over Bluetooth (${g.device.address})")
            }
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
            synchronized(writeQueue) { writing = false }
            pumpWrites(g)
        }

        // Android 13+
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray) {
            if (c.uuid == TX) received(value)
        }

        // Android 8-12
        @Deprecated("Deprecated in Java")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            if (Build.VERSION.SDK_INT >= 33) return       // handled by the method above
            @Suppress("DEPRECATION")
            val v = c.value ?: return
            if (c.uuid == TX) received(v)
        }
    }

    private fun received(bytes: ByteArray) {
        val lines = mutableListOf<String>()
        synchronized(incoming) {
            incoming.append(String(bytes, Charsets.UTF_8))
            var nl = incoming.indexOf("\n")
            while (nl >= 0) {
                val line = incoming.substring(0, nl).trim()
                if (line.isNotEmpty()) lines.add(line)
                incoming.delete(0, nl + 1)
                nl = incoming.indexOf("\n")
            }
            if (incoming.length > 4096) incoming.setLength(0)   // garbage guard
        }
        lines.forEach(onLine)
    }

    private fun pumpWrites(g: BluetoothGatt) {
        val c = rx ?: return
        val next: ByteArray
        synchronized(writeQueue) {
            if (writing || writeQueue.isEmpty()) return
            next = writeQueue.poll() ?: return
            writing = true
        }
        val ok = if (Build.VERSION.SDK_INT >= 33) {
            g.writeCharacteristic(c, next, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothGatt.GATT_SUCCESS
        } else {
            @Suppress("DEPRECATION")
            c.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            @Suppress("DEPRECATION")
            c.value = next
            @Suppress("DEPRECATION")
            g.writeCharacteristic(c)
        }
        if (!ok) {
            // the stack was busy: put it back and try again shortly
            synchronized(writeQueue) { writeQueue.addFirst(next); writing = false }
            handler.postDelayed({ gatt?.let { pumpWrites(it) } }, 30)
        }
    }
}
