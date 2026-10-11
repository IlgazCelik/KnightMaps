import { registerPlugin, Capacitor, WebPlugin } from '@capacitor/core';

// Native side: native-android/WifiScanPlugin.java
// Web side: browsers have no API to scan Wi-Fi, so the web build reports "unsupported".
class WifiScanWeb extends WebPlugin {
  async scan() {
    return { supported: false, fresh: false, networks: [] };
  }
  async saveJson() {
    return { path: '' };
  }
  async deleteJson() {}
  async startGps() {}
  async stopGps() {}
  async getLocation() {
    throw this.unavailable('GPS only works in the Android app.');
  }
  async uploadImage() {
    throw this.unavailable('Photo upload only works in the Android app.');
  }
  async startMotion() {
    throw this.unavailable('Motion tracking only works in the Android app.');
  }
  async getDisplacement() {
    return { east: 0, north: 0, steps: 0 };
  }
  async stopMotion() {}
  async startListening() {
    throw this.unavailable('Voice search only works in the Android app.');
  }
  async stopListening() {}
  async getHeading() {
    throw this.unavailable('Orientation only works in the Android app.');
  }
}

export const WifiScan = registerPlugin('WifiScan', { web: () => new WifiScanWeb() });

export const isNative = Capacitor.isNativePlatform();
