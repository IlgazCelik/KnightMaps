# WiFi Scanner (Capacitor: Android app + website)

Continuously scans nearby Wi-Fi and prints SSID, BSSID and RSSI.

## Requirements
- Node.js 20+ (`brew install node`)
- Android Studio (with its bundled JDK 21)

## Website
    npm install
    npm run dev        # http://localhost:5173

Browsers have no Wi-Fi scanning API, so the website shows a "not available" notice.
Real scan data only comes from the Android app.

## Android
    ./setup-android.sh     # one time
    npx cap open android   # then press Run in Android Studio

After editing web code:  `npm run android`

On the phone: allow the location permission and keep Location services ON
(Android requires it to return Wi-Fi scan results).

Output appears on screen and in Logcat (filter by `WifiScan` or `Capacitor/Console`).

## Layout
    index.html, src/          shared web UI (app + website)
    src/wifi.js               plugin bridge, web fallback
    native-android/           native Wi-Fi plugin, copied into android/ by setup script
    capacitor.config.json
