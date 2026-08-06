'use client';

import imageCompression from 'browser-image-compression';

/**
 * Client-side image compression before upload. Targets < 500KB per image and
 * caps the longest edge so invite pages stay fast on mobile connections.
 */
export async function compressForUpload(file: File): Promise<File> {
  if (!file.type.startsWith('image/')) return file;
  try {
    const compressed = await imageCompression(file, {
      maxSizeMB: 0.5, // ~500KB target
      maxWidthOrHeight: 2000,
      useWebWorker: true,
      fileType: file.type === 'image/png' ? 'image/png' : 'image/jpeg',
      initialQuality: 0.8
    });
    // Preserve a sensible filename/extension for the storage key.
    return new File([compressed], file.name, { type: compressed.type });
  } catch {
    // If compression fails, fall back to the original rather than blocking upload.
    return file;
  }
}
