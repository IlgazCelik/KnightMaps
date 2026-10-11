import { WifiScan } from './wifi.js';

// Outside mode: live camera preview; the shutter takes a picture and uploads it to the server
// (multipart/form-data, file field "image", like `curl -F image=@photo.jpg`).
export const UPLOAD_URL = 'http://10.42.0.1:5000/api/upload';
const MAX_SIDE = 1280;     // resize so a photo is ~150-300 KB instead of several MB
const JPEG_QUALITY = 0.7;

const video = document.getElementById('camera');
let stream = null;

export async function startCamera() {
  if (stream) return;
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
    audio: false,
  });
  video.srcObject = stream;
  await video.play();
  video.hidden = false;
}

export function stopCamera() {
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = null;
  video.srcObject = null;
  video.hidden = true;
}

// Resizes an image source (camera frame or picked photo) to at most MAX_SIDE, encodes it as JPEG and uploads
// it with the given text fields. Returns { message, body }: body is the server's reply when it succeeded.
async function encodeAndSend(source, width, height, fields) {
  const k = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * k);
  canvas.height = Math.round(height * k);
  canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
  const base64 = canvas.toDataURL('image/jpeg', JPEG_QUALITY).split(',')[1];
  try {
    const { status, body } = await WifiScan.uploadImage({
      url: UPLOAD_URL, base64, filename: `photo_${Date.now()}.jpg`,
      fields: { timestamp: String(Date.now() / 1000), ...fields },
    });
    console.log(`Upload response (${status}): ${body}`);
    return status >= 200 && status < 300 ? { message: '', body } : { message: `Server error ${status}`, body: null };
  } catch {
    return { message: "Can't reach the server", body: null };
  }
}

// Takes the current camera frame and uploads it.
export async function takeAndSend(fields = {}) {
  if (!stream || !video.videoWidth) return { message: 'Camera not ready', body: null };
  return encodeAndSend(video, video.videoWidth, video.videoHeight, { source: 'camera', ...fields });
}

// Uploads a picture chosen from the phone (turned upright using its EXIF orientation).
export async function sendPickedImage(file, fields = {}) {
  let img;
  try {
    img = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    return { message: "Couldn't open that picture", body: null };
  }
  const result = await encodeAndSend(img, img.width, img.height, { source: 'upload', ...fields });
  img.close();
  return result;
}
