package com.example.wifiscanner;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.database.Cursor;
import android.hardware.GeomagneticField;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.Uri;
import android.net.wifi.ScanResult;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.Bundle;
import android.provider.MediaStore;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.util.Log;

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

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Iterator;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

@CapacitorPlugin(
    name = "WifiScan",
    permissions = {
        @Permission(alias = "location", strings = {
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        }),
        @Permission(alias = "microphone", strings = { Manifest.permission.RECORD_AUDIO })
    }
)
public class WifiScanPlugin extends Plugin {

    private static final String TAG = "WifiScan";
    private static final long SCAN_TIMEOUT_MS = 10000;
    private static final long HEADING_SAMPLE_MS = 400;
    // Used for the magnetic-to-true-north correction when the phone has no last known location.
    private static final double UCF_LAT = 28.6024, UCF_LON = -81.2001;

    private final Handler handler = new Handler(Looper.getMainLooper());

    // Send all of this app's traffic over Wi-Fi. A computer-hosted hotspot has no internet, so
    // Android would otherwise keep using mobile data and the local server (e.g. 10.42.0.1) is unreachable.
    @Override
    public void load() {
        ConnectivityManager cm = (ConnectivityManager) getContext().getSystemService(Context.CONNECTIVITY_SERVICE);
        NetworkRequest wifi = new NetworkRequest.Builder()
                .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build();
        cm.registerNetworkCallback(wifi, new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network network) {
                cm.bindProcessToNetwork(network);
                Log.d(TAG, "App traffic bound to Wi-Fi " + network);
            }

            @Override
            public void onLost(Network network) {
                if (network.equals(cm.getBoundNetworkForProcess())) cm.bindProcessToNetwork(null);
            }
        });
    }

    @PluginMethod
    public void scan(PluginCall call) {
        if (getPermissionState("location") != PermissionState.GRANTED) {
            requestPermissionForAlias("location", call, "locationPermCallback");
            return;
        }
        doScan(call);
    }

    @PermissionCallback
    private void locationPermCallback(PluginCall call) {
        if (getPermissionState("location") == PermissionState.GRANTED) {
            doScan(call);
        } else {
            call.reject("Location permission is required to scan Wi-Fi");
        }
    }

    // Starts a fresh scan and waits for its results (up to SCAN_TIMEOUT_MS).
    // If Android throttles the scan, falls back to the latest cached results and reports fresh=false.
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
                boolean fresh = intent.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED, false);
                resolveResults(call, wifi.getScanResults(), fresh);
            }
        };
        ContextCompat.registerReceiver(ctx, receiver,
                new IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION),
                ContextCompat.RECEIVER_EXPORTED);

        Runnable fallback = () -> {
            if (!done.compareAndSet(false, true)) return;
            ctx.unregisterReceiver(receiver);
            resolveResults(call, wifi.getScanResults(), false);
        };

        if (wifi.startScan()) {
            handler.postDelayed(fallback, SCAN_TIMEOUT_MS);
        } else {
            Log.w(TAG, "startScan throttled, using cached results");
            fallback.run();
        }
    }

    private void resolveResults(PluginCall call, List<ScanResult> results, boolean fresh) {
        JSArray networks = new JSArray();
        for (ScanResult r : results) {
            JSObject n = new JSObject();
            n.put("ssid", r.SSID);
            n.put("bssid", r.BSSID);
            n.put("rssi", r.level);
            n.put("frequency", r.frequency);
            networks.put(n);
        }
        JSObject ret = new JSObject();
        ret.put("supported", true);
        ret.put("fresh", fresh);
        ret.put("networks", networks);
        call.resolve(ret);
    }

    // Writes one scan to Downloads/<name> (e.g. wifi_scan_3.json), replacing a file of that name this app made before.
    @PluginMethod
    public void saveJson(PluginCall call) {
        if (Build.VERSION.SDK_INT < 29) {
            call.reject("Saving to Downloads needs Android 10 or newer");
            return;
        }
        String name = call.getString("name");
        String json = call.getString("json", "{}");
        if (name == null || !name.matches("[A-Za-z0-9_.-]+\\.json")) {
            call.reject("Invalid file name: " + name);
            return;
        }
        ContentResolver resolver = getContext().getContentResolver();
        try {
            Uri uri = findExport(resolver, name);
            if (uri == null) {
                ContentValues values = new ContentValues();
                values.put(MediaStore.Downloads.DISPLAY_NAME, name);
                values.put(MediaStore.Downloads.MIME_TYPE, "application/json");
                values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/");
                uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (uri == null) throw new IOException("MediaStore refused to create the file");
            }
            try (OutputStream out = resolver.openOutputStream(uri, "wt")) {
                out.write(json.getBytes(StandardCharsets.UTF_8));
            }
        } catch (IOException e) {
            call.reject("Could not save: " + e.getMessage());
            return;
        }
        JSObject ret = new JSObject();
        ret.put("path", "Download/" + name);
        call.resolve(ret);
    }

    // Deletes every wifi_scan*.json this app has saved to Downloads.
    @PluginMethod
    public void deleteJson(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 29) {
            String selection = MediaStore.Downloads.DISPLAY_NAME + " LIKE ? ESCAPE '\\' AND "
                    + MediaStore.Downloads.RELATIVE_PATH + "=?";
            String[] args = { "wifi\\_scan%.json", Environment.DIRECTORY_DOWNLOADS + "/" };
            getContext().getContentResolver().delete(MediaStore.Downloads.EXTERNAL_CONTENT_URI, selection, args);
        }
        call.resolve();
    }

    // Finds a file of this name that this app saved to Downloads earlier (apps can always see their own MediaStore files).
    private Uri findExport(ContentResolver resolver, String name) {
        String[] projection = { MediaStore.Downloads._ID };
        String selection = MediaStore.Downloads.DISPLAY_NAME + "=? AND " + MediaStore.Downloads.RELATIVE_PATH + "=?";
        String[] args = { name, Environment.DIRECTORY_DOWNLOADS + "/" };
        try (Cursor c = resolver.query(MediaStore.Downloads.EXTERNAL_CONTENT_URI, projection, selection, args, null)) {
            if (c != null && c.moveToFirst()) {
                return ContentUris.withAppendedId(MediaStore.Downloads.EXTERNAL_CONTENT_URI, c.getLong(0));
            }
        }
        return null;
    }

    // ---- Orientation: degrees clockwise from TRUE north (0 = north, 90 = east) that the phone points --
    // the camera direction when held up, the top edge when flat (see facing). Averages the sensor briefly.

    @PluginMethod
    public void getHeading(PluginCall call) {
        SensorManager sm = (SensorManager) getContext().getSystemService(Context.SENSOR_SERVICE);
        Sensor rotation = sm.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR);
        if (rotation == null) {
            call.reject("This phone has no rotation sensor");
            return;
        }
        double[] sum = new double[2];   // summed unit vectors (east, north) -- a circular average
        int[] count = new int[1];
        float[] r = new float[9];
        SensorEventListener listener = new SensorEventListener() {
            @Override
            public void onSensorChanged(SensorEvent e) {
                SensorManager.getRotationMatrixFromVector(r, e.values);
                double[] f = facing(r);
                if (f == null) return;   // no usable direction
                sum[0] += f[0];
                sum[1] += f[1];
                count[0]++;
            }

            @Override
            public void onAccuracyChanged(Sensor s, int accuracy) {}
        };
        sm.registerListener(listener, rotation, SensorManager.SENSOR_DELAY_GAME);
        handler.postDelayed(() -> {
            sm.unregisterListener(listener);
            if (count[0] == 0) {
                call.reject("No heading: hold the phone flat or upright");
                return;
            }
            double magnetic = Math.toDegrees(Math.atan2(sum[0], sum[1]));
            double declination = declination();
            double heading = ((magnetic + declination) % 360 + 360) % 360;
            JSObject ret = new JSObject();
            ret.put("heading", Math.round(heading * 10) / 10.0);
            ret.put("declination", Math.round(declination * 10) / 10.0);
            call.resolve(ret);
        }, HEADING_SAMPLE_MS);
    }

    /**
     * Which way the phone points, as a horizontal unit vector (east, north), from its rotation matrix r:
     * held up (tilted more than ~30 deg from flat) it's where the camera looks (out of the back, device -z);
     * held flat it's where the top edge points (device y). null if neither gives a usable direction.
     */
    private static double[] facing(float[] r) {
        double ce = -r[2], cn = -r[5], cl = Math.hypot(ce, cn);   // camera direction, horizontal part
        if (cl > 0.5) return new double[]{ce / cl, cn / cl};
        double te = r[1], tn = r[4], tl = Math.hypot(te, tn);     // top edge, horizontal part
        if (tl > 0.15) return new double[]{te / tl, tn / tl};
        return null;
    }

    /** Degrees true north is east of magnetic north here (negative = west), from the last known location. */
    @SuppressWarnings("MissingPermission")   // location permission is already granted for Wi-Fi scanning
    private double declination() {
        double lat = UCF_LAT, lon = UCF_LON, alt = 0;
        try {
            LocationManager lm = (LocationManager) getContext().getSystemService(Context.LOCATION_SERVICE);
            Location best = null;
            for (String provider : lm.getProviders(true)) {
                Location l = lm.getLastKnownLocation(provider);
                if (l != null && (best == null || l.getTime() > best.getTime())) best = l;
            }
            if (best != null) { lat = best.getLatitude(); lon = best.getLongitude(); alt = best.getAltitude(); }
        } catch (SecurityException ignored) {
            // fall back to UCF's coordinates
        }
        return new GeomagneticField((float) lat, (float) lon, (float) alt, System.currentTimeMillis()).getDeclination();
    }

    // ---- Pedestrian dead reckoning: steps from the accelerometer, step length from the Weinberg
    // method, direction from the compass (true north). Steps are kept with wall-clock times so the
    // app can ask "how far, and which way, since time T".

    private static final float STEP_K = 0.48f;           // Weinberg constant (per person/phone placement)
    private static final long MIN_STEP_MS = 250, MAX_STEP_MS = 2000, KEEP_MS = 120_000;
    private static final float STEP_RISE = 1.2f;          // m/s^2 above gravity that counts as a step peak

    private final ArrayDeque<double[]> steps = new ArrayDeque<>();   // {timeMs, eastM, northM}
    private SensorEventListener motionListener;
    private final float[] motionR = new float[9];
    private double headingDeg = Double.NaN, declinationDeg = 0;
    private float smoothA = SensorManager.GRAVITY_EARTH, prevA = SensorManager.GRAVITY_EARTH;
    private float winMax = 0, winMin = Float.MAX_VALUE;
    private boolean rising = false;
    private long lastStepMs = 0;
    private double stepPeriodMs = 0, lastStepLen = 0;   // walking rhythm, for showing motion between steps

    @PluginMethod
    public void startMotion(PluginCall call) {
        SensorManager sm = (SensorManager) getContext().getSystemService(Context.SENSOR_SERVICE);
        Sensor accel = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
        Sensor rotation = sm.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR);
        if (accel == null || rotation == null) {
            call.reject("This phone lacks an accelerometer or rotation sensor");
            return;
        }
        stopMotionSensors();
        synchronized (steps) { steps.clear(); }
        declinationDeg = declination();
        headingDeg = Double.NaN;
        lastStepMs = 0;
        stepPeriodMs = 0;
        lastStepLen = 0;
        winMax = 0;
        winMin = Float.MAX_VALUE;
        motionListener = new SensorEventListener() {
            @Override
            public void onSensorChanged(SensorEvent e) {
                if (e.sensor.getType() == Sensor.TYPE_ROTATION_VECTOR) {
                    SensorManager.getRotationMatrixFromVector(motionR, e.values);
                    double[] f = facing(motionR);
                    if (f != null) headingDeg = Math.toDegrees(Math.atan2(f[0], f[1])) + declinationDeg;
                    return;
                }
                float a = (float) Math.sqrt(e.values[0] * e.values[0] + e.values[1] * e.values[1] + e.values[2] * e.values[2]);
                smoothA += 0.25f * (a - smoothA);   // low-pass: keep the walking bounce, drop jitter
                winMax = Math.max(winMax, smoothA);
                winMin = Math.min(winMin, smoothA);
                long now = System.currentTimeMillis();
                // A step = a peak in the smoothed magnitude that rises clearly above gravity.
                if (smoothA > prevA) {
                    rising = true;
                } else if (rising && prevA > SensorManager.GRAVITY_EARTH + STEP_RISE
                        && now - lastStepMs > MIN_STEP_MS && !Double.isNaN(headingDeg)) {
                    rising = false;
                    if (lastStepMs != 0 && now - lastStepMs < MAX_STEP_MS) {
                        double len = STEP_K * Math.pow(Math.max(winMax - winMin, 0), 0.25);
                        long gap = now - lastStepMs;
                        stepPeriodMs = stepPeriodMs == 0 ? gap : stepPeriodMs + 0.3 * (gap - stepPeriodMs);
                        lastStepLen = len;
                        double h = Math.toRadians(headingDeg);
                        synchronized (steps) {
                            steps.addLast(new double[]{now, len * Math.sin(h), len * Math.cos(h)});
                            while (!steps.isEmpty() && now - steps.peekFirst()[0] > KEEP_MS) steps.removeFirst();
                        }
                    }
                    lastStepMs = now;
                    winMax = 0;
                    winMin = Float.MAX_VALUE;
                } else if (smoothA < prevA) {
                    rising = false;
                }
                prevA = smoothA;
            }

            @Override
            public void onAccuracyChanged(Sensor s, int accuracy) {}
        };
        sm.registerListener(motionListener, accel, SensorManager.SENSOR_DELAY_GAME);
        sm.registerListener(motionListener, rotation, SensorManager.SENSOR_DELAY_GAME);
        call.resolve();
    }

    // Distance moved since `since` (epoch ms): metres east and north, and the number of steps; plus the
    // walking rhythm (time of the last step, average step period, last step length, current true heading)
    // so the app can show movement part-way through the next step.
    @PluginMethod
    public void getDisplacement(PluginCall call) {
        double since = call.getDouble("since", 0.0);
        double east = 0, north = 0, recentEast = 0, recentNorth = 0, distance = 0;
        int count = 0;
        long nowMs = System.currentTimeMillis();
        synchronized (steps) {
            for (double[] st : steps) {
                if (st[0] > since) { east += st[1]; north += st[2]; distance += Math.hypot(st[1], st[2]); count++; }
                if (nowMs - st[0] < 2000) { recentEast += st[1]; recentNorth += st[2]; }   // last ~2 s of steps
            }
        }
        JSObject ret = new JSObject();
        ret.put("east", east);
        ret.put("north", north);
        ret.put("steps", count);
        ret.put("distance", distance);         // metres walked since `since` (sum of step lengths)
        ret.put("now", (double) System.currentTimeMillis());
        ret.put("lastStep", (double) lastStepMs);
        ret.put("stepPeriod", stepPeriodMs);
        ret.put("stride", lastStepLen);
        ret.put("heading", Double.isNaN(headingDeg) ? null : headingDeg);
        ret.put("recentEast", recentEast);     // where the last ~2 s of steps went: the walking direction
        ret.put("recentNorth", recentNorth);
        call.resolve(ret);
    }

    @PluginMethod
    public void stopMotion(PluginCall call) {
        stopMotionSensors();
        call.resolve();
    }

    private void stopMotionSensors() {
        if (motionListener != null) {
            ((SensorManager) getContext().getSystemService(Context.SENSOR_SERVICE)).unregisterListener(motionListener);
            motionListener = null;
        }
    }

    @Override
    protected void handleOnDestroy() {
        stopMotionSensors();
    }

    // ---- Photo upload: multipart/form-data POST (file field "image" + any extra text fields), the
    // same as a browser form or curl -F. Done natively so it doesn't depend on the web layer's HTTP.

    @PluginMethod
    public void uploadImage(PluginCall call) {
        String url = call.getString("url");
        String b64 = call.getString("base64", "");
        String filename = call.getString("filename", "photo.jpg");
        JSObject fields = call.getObject("fields", new JSObject());
        String boundary = "----KnightMaps" + System.currentTimeMillis();
        HttpURLConnection conn = null;
        try {
            byte[] image = android.util.Base64.decode(b64, android.util.Base64.DEFAULT);
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            for (Iterator<String> it = fields.keys(); it.hasNext(); ) {
                String k = it.next();
                body.write(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + k + "\"\r\n\r\n"
                        + fields.getString(k) + "\r\n").getBytes(StandardCharsets.UTF_8));
            }
            body.write(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"image\"; filename=\"" + filename
                    + "\"\r\nContent-Type: image/jpeg\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            body.write(image);
            body.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));

            conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(15000);
            conn.setDoOutput(true);
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
            conn.setFixedLengthStreamingMode(body.size());
            try (OutputStream out = conn.getOutputStream()) {
                body.writeTo(out);
            }
            int status = conn.getResponseCode();
            InputStream in = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String reply = "";
            if (in != null) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] chunk = new byte[4096];
                for (int n; (n = in.read(chunk)) > 0; ) buf.write(chunk, 0, n);
                reply = buf.toString("UTF-8");
            }
            JSObject ret = new JSObject();
            ret.put("status", status);
            ret.put("body", reply);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Upload failed: " + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    // ---- GPS for Outside mode: kept running while Outside is shown, so a picture can be sent with a
    // current fix instead of waiting for one.

    private LocationListener gpsListener;
    private Location lastFix;

    @SuppressWarnings("MissingPermission")   // location permission is already granted for Wi-Fi scanning
    @PluginMethod
    public void startGps(PluginCall call) {
        LocationManager lm = (LocationManager) getContext().getSystemService(Context.LOCATION_SERVICE);
        stopGpsUpdates();
        gpsListener = loc -> {
            if (lastFix == null || loc.getTime() >= lastFix.getTime()) lastFix = loc;
        };
        try {
            for (String provider : new String[]{LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER}) {
                if (lm.isProviderEnabled(provider)) {
                    lm.requestLocationUpdates(provider, 1000, 0, gpsListener, Looper.getMainLooper());
                    Location known = lm.getLastKnownLocation(provider);
                    if (known != null && (lastFix == null || known.getTime() > lastFix.getTime())) lastFix = known;
                }
            }
            call.resolve();
        } catch (SecurityException e) {
            call.reject("Location permission missing");
        }
    }

    @PluginMethod
    public void stopGps(PluginCall call) {
        stopGpsUpdates();
        call.resolve();
    }

    private void stopGpsUpdates() {
        if (gpsListener != null) {
            ((LocationManager) getContext().getSystemService(Context.LOCATION_SERVICE)).removeUpdates(gpsListener);
            gpsListener = null;
        }
    }

    // Latest fix: latitude/longitude (degrees), accuracy (m, 68% radius), altitude (m, if known), time (epoch ms),
    // provider ("gps" or "network"). Rejects if there's no fix yet.
    @PluginMethod
    public void getLocation(PluginCall call) {
        Location f = lastFix;
        if (f == null) {
            call.reject("No location fix yet");
            return;
        }
        JSObject ret = new JSObject();
        ret.put("latitude", f.getLatitude());
        ret.put("longitude", f.getLongitude());
        ret.put("accuracy", f.hasAccuracy() ? (double) f.getAccuracy() : null);
        ret.put("altitude", f.hasAltitude() ? f.getAltitude() : null);
        ret.put("time", (double) f.getTime());
        ret.put("provider", f.getProvider());
        call.resolve(ret);
    }

    // ---- Voice search: Android's built-in speech-to-text. Listens until stopListening(); Android ends a
    // session after each pause, so it restarts and keeps adding to the text. Sends "speech" events
    // {text, final} as words come in, and {text, final: true, stopped: true} at the end.
    private SpeechRecognizer recognizer;
    private boolean listening = false;
    private String spokenSoFar = "";   // finished phrases from earlier sessions
    private String partial = "";       // the phrase being spoken now

    @PluginMethod
    public void startListening(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "micPermCallback");
            return;
        }
        beginListening(call);
    }

    @PermissionCallback
    private void micPermCallback(PluginCall call) {
        if (getPermissionState("microphone") == PermissionState.GRANTED) beginListening(call);
        else call.reject("Microphone permission is needed for voice search");
    }

    private void beginListening(PluginCall call) {
        handler.post(() -> {
            if (!SpeechRecognizer.isRecognitionAvailable(getContext())) {
                call.reject("Speech recognition isn't available on this phone");
                return;
            }
            spokenSoFar = "";
            partial = "";
            listening = true;
            startSession();
            call.resolve();
        });
    }

    @PluginMethod
    public void stopListening(PluginCall call) {
        handler.post(() -> {
            if (listening) finishListening();
            call.resolve();
        });
    }

    private void finishListening() {
        listening = false;
        if (recognizer != null) {
            recognizer.cancel();
            recognizer.destroy();
            recognizer = null;
        }
        String text = joined();
        spokenSoFar = text;
        partial = "";
        sendSpeech(text, true, true);
    }

    private String joined() {
        return (spokenSoFar + " " + partial).trim();
    }

    private void sendSpeech(String text, boolean isFinal, boolean stopped) {
        JSObject ev = new JSObject();
        ev.put("text", text);
        ev.put("final", isFinal);
        ev.put("stopped", stopped);
        notifyListeners("speech", ev);
    }

    private void startSession() {
        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(getContext());
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle b) {}
                @Override public void onBeginningOfSpeech() {}
                @Override public void onRmsChanged(float v) {}
                @Override public void onBufferReceived(byte[] b) {}
                @Override public void onEndOfSpeech() {}
                @Override public void onEvent(int t, Bundle b) {}

                @Override public void onPartialResults(Bundle b) {
                    ArrayList<String> r = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (!listening || r == null || r.isEmpty()) return;
                    partial = r.get(0);
                    sendSpeech(joined(), false, false);
                }

                @Override public void onResults(Bundle b) {
                    ArrayList<String> r = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (r != null && !r.isEmpty()) partial = r.get(0);
                    spokenSoFar = joined();
                    partial = "";
                    if (!listening) return;
                    sendSpeech(spokenSoFar, false, false);
                    startSession();   // still on: keep listening after the pause
                }

                @Override public void onError(int error) {
                    if (!listening) return;
                    switch (error) {
                        case SpeechRecognizer.ERROR_NO_MATCH:
                        case SpeechRecognizer.ERROR_SPEECH_TIMEOUT:
                        case SpeechRecognizer.ERROR_RECOGNIZER_BUSY:
                            handler.postDelayed(() -> { if (listening) startSession(); }, 250);   // silence: keep going
                            break;
                        default:
                            Log.w(TAG, "speech error " + error);
                            finishListening();
                    }
                }
            });
        }
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 3000L);
        recognizer.startListening(intent);
    }
}
