// Camera on the Android app (Capacitor). The system asks for the camera permission the first time.
// In a browser this module is not used; the photo step falls back to a file input.
import { Capacitor } from "@capacitor/core";
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";

export function isNativeApp(): boolean {
  return Capacitor.isNativePlatform();
}

/** Open the phone's camera and return the photo as a File. Returns null when the user cancels. */
export async function takePhotoNative(): Promise<File | null> {
  try {
    const photo = await Camera.getPhoto({
      source: CameraSource.Camera,
      resultType: CameraResultType.Uri,
      quality: 90,
      correctOrientation: true,
      saveToGallery: false,
    });
    if (!photo.webPath) return null;
    const blob = await (await fetch(photo.webPath)).blob();
    return new File([blob], `photo-${Date.now()}.jpg`, { type: blob.type || "image/jpeg" });
  } catch {
    // Cancelled by the user, or the camera is not available: nothing is added.
    return null;
  }
}
