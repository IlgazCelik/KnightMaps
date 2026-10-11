package com.example.rssimonitor;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.wifi.ScanResult;
import android.net.wifi.WifiManager;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;

import androidx.core.content.ContextCompat;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.util.concurrent.atomic.AtomicBoolean;

// Wi-Fi scan for the RSSI monitor: every access point heard, with the moment it was last heard (seenAt,
// epoch ms, from Android's own per-result timestamp) so repeated cached results can be told apart.
@CapacitorPlugin(
    name = "RssiScan",
    permissions = {
        @Permission(alias = "location", strings = {
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        })
    }
)
public class RssiPlugin extends Plugin {
    private static final long SCAN_TIMEOUT_MS = 10000;
    private final Handler handler = new Handler(Looper.getMainLooper());

    @PluginMethod
    public void scan(PluginCall call) {
        if (getPermissionState("location") != PermissionState.GRANTED) {
            requestPermissionForAlias("location", call, "permCallback");
            return;
        }
        doScan(call);
    }

    @PermissionCallback
    private void permCallback(PluginCall call) {
        if (getPermissionState("location") == PermissionState.GRANTED) doScan(call);
        else call.reject("Location permission is required to scan Wi-Fi");
    }

    @SuppressWarnings("deprecation")
    private void doScan(PluginCall call) {
        Context ctx = getContext().getApplicationContext();
        WifiManager wifi = (WifiManager) ctx.getSystemService(Context.WIFI_SERVICE);
        if (!wifi.isWifiEnabled()) {
            call.reject("Wi-Fi is turned off");
            return;
        }
        AtomicBoolean done = new AtomicBoolean(false);
        BroadcastReceiver receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent intent) {
                if (!done.compareAndSet(false, true)) return;
                ctx.unregisterReceiver(this);
                resolve(call, wifi, intent.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED, false));
            }
        };
        ContextCompat.registerReceiver(ctx, receiver, new IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION),
                ContextCompat.RECEIVER_EXPORTED);
        Runnable fallback = () -> {
            if (!done.compareAndSet(false, true)) return;
            ctx.unregisterReceiver(receiver);
            resolve(call, wifi, false);
        };
        if (wifi.startScan()) handler.postDelayed(fallback, SCAN_TIMEOUT_MS);
        else fallback.run();   // throttled by Android: return the latest cached results
    }

    private void resolve(PluginCall call, WifiManager wifi, boolean fresh) {
        long bootToEpoch = System.currentTimeMillis() - SystemClock.elapsedRealtime();
        JSArray list = new JSArray();
        for (ScanResult r : wifi.getScanResults()) {
            JSObject n = new JSObject();
            n.put("bssid", r.BSSID);
            n.put("ssid", r.SSID);
            n.put("rssi", r.level);
            n.put("frequency", r.frequency);
            n.put("seenAt", (double) (bootToEpoch + r.timestamp / 1000));   // ScanResult.timestamp: us since boot
            list.put(n);
        }
        JSObject ret = new JSObject();
        ret.put("fresh", fresh);
        ret.put("networks", list);
        call.resolve(ret);
    }
}
