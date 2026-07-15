export const MAX_WORK_UPLOAD_BYTES = 500 * 1024 * 1024;
export const MAX_WORK_IMAGE_COUNT = 10;
export const WORK_FILE_ACCEPT = "image/*,.pdf,application/pdf,video/mp4,video/webm,video/quicktime";

export function guessContentType(fileName) {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".mp4")) return "video/mp4";
  if (lower.endsWith(".webm")) return "video/webm";
  if (lower.endsWith(".mov")) return "video/quicktime";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".webp")) return "image/webp";
  return "image/jpeg";
}

function isImageFile(file) {
  const contentType = file.type || guessContentType(file.name);
  return contentType.startsWith("image/");
}

export function normalizeSelectedWorkFiles(fileList) {
  const files = Array.from(fileList ?? []);
  if (files.length === 0) {
    return { asset: null, images: [] };
  }

  const imageFiles = files.filter(isImageFile);
  const otherFiles = files.filter((file) => !isImageFile(file));

  if (imageFiles.length > 0 && otherFiles.length > 0) {
    return { error: "图片作品请只选择图片；PDF/视频请单独上传。" };
  }

  if (imageFiles.length > MAX_WORK_IMAGE_COUNT) {
    return { error: `最多只能上传 ${MAX_WORK_IMAGE_COUNT} 张图片。` };
  }

  if (otherFiles.length > 1) {
    return { error: "PDF 或视频一次只能上传 1 个文件。" };
  }

  const oversizedFile = files.find((file) => file.size > MAX_WORK_UPLOAD_BYTES);
  if (oversizedFile) {
    return { error: `${oversizedFile.name} 超过 500MB。` };
  }

  return { asset: otherFiles[0] ?? null, images: imageFiles };
}

function selectedFileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export function mergeSelectedWorkFiles(currentSelection, fileList) {
  const selected = normalizeSelectedWorkFiles(fileList);
  if (selected.error) {
    return selected;
  }

  const currentImages = currentSelection?.images || [];
  const currentAsset = currentSelection?.asset || null;

  if (selected.asset) {
    if (currentImages.length > 0) {
      return { error: "已经选择了图片。如需上传 PDF 或视频，请先移除全部图片。" };
    }
    return { asset: selected.asset, images: [] };
  }

  if (selected.images.length === 0) {
    return { asset: currentAsset, images: currentImages };
  }

  if (currentAsset) {
    return { error: "已经选择了 PDF 或视频。如需上传图片，请先移除当前附件。" };
  }

  const existingKeys = new Set(currentImages.map(selectedFileKey));
  const newImages = selected.images.filter((file) => {
    const key = selectedFileKey(file);
    if (existingKeys.has(key)) return false;
    existingKeys.add(key);
    return true;
  });
  const images = [...currentImages, ...newImages];

  if (images.length > MAX_WORK_IMAGE_COUNT) {
    return { error: `当前已有 ${currentImages.length} 张，最多只能上传 ${MAX_WORK_IMAGE_COUNT} 张图片。` };
  }

  if (newImages.length === 0) {
    return { error: "这些图片已经添加过了，请选择其他图片。" };
  }

  return { asset: null, images };
}
