#!/bin/sh
# One-time: creates the android/ project and drops in the native Wi-Fi plugin + permissions.
set -e
cd "$(dirname "$0")"

npm install
npm run build
[ -d android ] || npx cap add android

JAVA_DIR=android/app/src/main/java/com/example/wifiscanner
cp native-android/WifiScanPlugin.java native-android/MainActivity.java "$JAVA_DIR/"

MANIFEST=android/app/src/main/AndroidManifest.xml
if ! grep -q ACCESS_FINE_LOCATION "$MANIFEST"; then
  perl -0pi -e 's#(\s*<application)#
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
$1#' "$MANIFEST"
fi

# allow plain http:// to the local scan server
grep -q usesCleartextTraffic "$MANIFEST" || perl -0pi -e 's#<application#<application\n        android:usesCleartextTraffic="true"#' "$MANIFEST"

npx cap sync android
echo "Done. Run: npx cap open android"
