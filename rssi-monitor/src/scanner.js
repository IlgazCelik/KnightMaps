import { registerPlugin, WebPlugin } from '@capacitor/core';

// Native side: native-android/RssiPlugin.java. Browsers can't scan Wi-Fi.
class RssiScanWeb extends WebPlugin {
  async scan() {
    throw this.unavailable('Wi-Fi scanning only works in the Android app.');
  }
}
export const RssiScan = registerPlugin('RssiScan', { web: () => new RssiScanWeb() });
