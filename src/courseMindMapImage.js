export const COURSE_MIND_MAP_MAX_BYTES = 10 * 1024 * 1024;
export const COURSE_MIND_MAP_MAX_PIXELS = 40_000_000;

const COURSE_MIND_MAP_SOURCE_MAX_BYTES = 60 * 1024 * 1024;
export const COURSE_MIND_MAP_SOURCE_MAX_PIXELS = 150_000_000;
export const COURSE_MIND_MAP_SOURCE_MAX_EDGE = 24_000;
const COURSE_MIND_MAP_TARGET_BYTES = 9 * 1024 * 1024;
const COURSE_MIND_MAP_TARGET_PIXELS = 20_000_000;
const COURSE_MIND_MAP_TARGET_MAX_EDGE = 8192;
const WEBP_QUALITIES = [0.92, 0.84, 0.76];

function readUint16BigEndian(bytes, offset) {
  return (bytes[offset] << 8) | bytes[offset + 1];
}

function readUint24LittleEndian(bytes, offset) {
  return bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16);
}

function readUint32LittleEndian(bytes, offset) {
  return (
    bytes[offset]
    | (bytes[offset + 1] << 8)
    | (bytes[offset + 2] << 16)
    | (bytes[offset + 3] << 24)
  ) >>> 0;
}

function chunkName(bytes, offset) {
  return String.fromCharCode(bytes[offset], bytes[offset + 1], bytes[offset + 2], bytes[offset + 3]);
}

function parsePngDimensions(bytes) {
  const isPng = bytes.length >= 24
    && bytes[0] === 0x89
    && bytes[1] === 0x50
    && bytes[2] === 0x4e
    && bytes[3] === 0x47
    && bytes[4] === 0x0d
    && bytes[5] === 0x0a
    && bytes[6] === 0x1a
    && bytes[7] === 0x0a
    && bytes[8] === 0x00
    && bytes[9] === 0x00
    && bytes[10] === 0x00
    && bytes[11] === 0x0d
    && chunkName(bytes, 12) === "IHDR";
  if (!isPng) return null;

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return { width: view.getUint32(16), height: view.getUint32(20), format: "PNG" };
}

function parseJpegDimensions(bytes) {
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;

  const startOfFrameMarkers = new Set([
    0xc0, 0xc1, 0xc2, 0xc3,
    0xc5, 0xc6, 0xc7,
    0xc9, 0xca, 0xcb,
    0xcd, 0xce, 0xcf,
  ]);
  let offset = 2;

  while (offset + 8 < bytes.length) {
    if (bytes[offset] !== 0xff) {
      offset += 1;
      continue;
    }
    while (offset < bytes.length && bytes[offset] === 0xff) offset += 1;
    if (offset >= bytes.length) break;

    const marker = bytes[offset];
    offset += 1;
    if (marker === 0xd9 || marker === 0xda) break;
    if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
    if (offset + 1 >= bytes.length) break;

    const segmentLength = readUint16BigEndian(bytes, offset);
    if (segmentLength < 2 || offset + segmentLength > bytes.length) break;
    if (startOfFrameMarkers.has(marker) && segmentLength >= 7) {
      return {
        width: readUint16BigEndian(bytes, offset + 5),
        height: readUint16BigEndian(bytes, offset + 3),
        format: "JPEG",
      };
    }
    offset += segmentLength;
  }
  return null;
}

function parseWebpDimensions(bytes) {
  if (
    bytes.length < 30
    || chunkName(bytes, 0) !== "RIFF"
    || chunkName(bytes, 8) !== "WEBP"
  ) {
    return null;
  }

  let offset = 12;
  while (offset + 8 <= bytes.length) {
    const type = chunkName(bytes, offset);
    const chunkSize = readUint32LittleEndian(bytes, offset + 4);
    const dataOffset = offset + 8;

    if (type === "VP8X" && dataOffset + 10 <= bytes.length) {
      return {
        width: readUint24LittleEndian(bytes, dataOffset + 4) + 1,
        height: readUint24LittleEndian(bytes, dataOffset + 7) + 1,
        format: "WEBP",
      };
    }
    if (type === "VP8L" && dataOffset + 5 <= bytes.length && bytes[dataOffset] === 0x2f) {
      const packed = readUint32LittleEndian(bytes, dataOffset + 1);
      return {
        width: (packed & 0x3fff) + 1,
        height: ((packed >>> 14) & 0x3fff) + 1,
        format: "WEBP",
      };
    }
    if (
      type === "VP8 "
      && dataOffset + 10 <= bytes.length
      && bytes[dataOffset + 3] === 0x9d
      && bytes[dataOffset + 4] === 0x01
      && bytes[dataOffset + 5] === 0x2a
    ) {
      return {
        width: (bytes[dataOffset + 6] | (bytes[dataOffset + 7] << 8)) & 0x3fff,
        height: (bytes[dataOffset + 8] | (bytes[dataOffset + 9] << 8)) & 0x3fff,
        format: "WEBP",
      };
    }

    const nextOffset = dataOffset + chunkSize + (chunkSize % 2);
    if (nextOffset <= offset || nextOffset > bytes.length) break;
    offset = nextOffset;
  }
  return null;
}

export function parseImageDimensions(bytes) {
  return parsePngDimensions(bytes) || parseJpegDimensions(bytes) || parseWebpDimensions(bytes);
}

async function readImageDimensions(file) {
  const initialLength = Math.min(file.size, 256 * 1024);
  let bytes = new Uint8Array(await file.slice(0, initialLength).arrayBuffer());
  let dimensions = parseImageDimensions(bytes);

  if (!dimensions && initialLength < file.size) {
    bytes = new Uint8Array(await file.arrayBuffer());
    dimensions = parseImageDimensions(bytes);
  }
  if (!dimensions?.width || !dimensions?.height) {
    throw new Error("无法读取图片尺寸，请确认文件是有效的 JPG、PNG 或 WebP 图片。");
  }
  return dimensions;
}

export function calculateMindMapResize(
  width,
  height,
  { maxPixels = COURSE_MIND_MAP_TARGET_PIXELS, maxEdge = COURSE_MIND_MAP_TARGET_MAX_EDGE } = {},
) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new TypeError("图片宽高必须是正数");
  }

  const scale = Math.min(
    1,
    Math.sqrt(maxPixels / (width * height)),
    maxEdge / width,
    maxEdge / height,
  );
  const targetWidth = Math.max(1, Math.floor(width * scale));
  const targetHeight = Math.max(1, Math.floor(height * scale));

  return {
    width: targetWidth,
    height: targetHeight,
    scale,
    resized: targetWidth !== width || targetHeight !== height,
  };
}

export function canAutoOptimizeCourseMindMap(width, height) {
  return width <= COURSE_MIND_MAP_SOURCE_MAX_EDGE
    && height <= COURSE_MIND_MAP_SOURCE_MAX_EDGE
    && width * height <= COURSE_MIND_MAP_SOURCE_MAX_PIXELS;
}

export function courseMindMapWebpName(filename = "思维导图") {
  const baseName = filename.replace(/\.[^.]+$/, "") || "思维导图";
  return `${baseName}-已优化.webp`;
}

function canvasToWebp(canvas, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob || blob.type !== "image/webp") {
        reject(new Error("当前浏览器无法生成 WebP 图片，请使用最新版 Chrome 或 Edge 后重试。"));
        return;
      }
      resolve(blob);
    }, "image/webp", quality);
  });
}

async function encodeWithinLimit(bitmap, initialWidth, initialHeight) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) throw new Error("浏览器无法创建图片处理画布。");

  let width = initialWidth;
  let height = initialHeight;
  let smallestBlob = null;

  try {
    for (let round = 0; round < 3; round += 1) {
      canvas.width = width;
      canvas.height = height;
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.clearRect(0, 0, width, height);
      context.drawImage(bitmap, 0, 0, width, height);

      for (const quality of WEBP_QUALITIES) {
        const blob = await canvasToWebp(canvas, quality);
        if (!smallestBlob || blob.size < smallestBlob.size) smallestBlob = blob;
        if (blob.size <= COURSE_MIND_MAP_TARGET_BYTES) return { blob, width, height };
      }

      const reduction = Math.min(
        0.82,
        Math.sqrt(COURSE_MIND_MAP_TARGET_BYTES / smallestBlob.size) * 0.9,
      );
      width = Math.max(1, Math.floor(width * reduction));
      height = Math.max(1, Math.floor(height * reduction));
    }
  } finally {
    canvas.width = 1;
    canvas.height = 1;
  }

  throw new Error("自动优化后图片仍然过大，请先压缩图片再上传。");
}

export async function optimizeCourseMindMapFile(file) {
  if (!file) throw new Error("请选择思维导图图片。");
  if (file.size > COURSE_MIND_MAP_SOURCE_MAX_BYTES) {
    throw new Error("原图不能超过 60MB，请先压缩图片再上传。");
  }

  const dimensions = await readImageDimensions(file);
  const pixelCount = dimensions.width * dimensions.height;
  if (!canAutoOptimizeCourseMindMap(dimensions.width, dimensions.height)) {
    throw new Error(
      `原图分辨率 ${dimensions.width} × ${dimensions.height} 超出自动优化范围`
      + "（总像素最多 1.5 亿、最长边 24000 像素），请先缩小图片后再上传。",
    );
  }
  const needsOptimization = file.size > COURSE_MIND_MAP_MAX_BYTES
    || pixelCount > COURSE_MIND_MAP_MAX_PIXELS;

  if (!needsOptimization) {
    return {
      file,
      optimized: false,
      originalWidth: dimensions.width,
      originalHeight: dimensions.height,
      width: dimensions.width,
      height: dimensions.height,
      originalSize: file.size,
    };
  }
  if (typeof createImageBitmap !== "function") {
    throw new Error("当前浏览器不支持超大图片自动优化，请使用最新版 Chrome 或 Edge 后重试。");
  }

  const target = calculateMindMapResize(dimensions.width, dimensions.height);
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, {
      resizeWidth: target.width,
      resizeHeight: target.height,
      resizeQuality: "high",
    });
    const bitmapTarget = calculateMindMapResize(bitmap.width, bitmap.height);
    const encoded = await encodeWithinLimit(bitmap, bitmapTarget.width, bitmapTarget.height);
    const optimizedFile = new File(
      [encoded.blob],
      courseMindMapWebpName(file.name),
      { type: "image/webp", lastModified: Date.now() },
    );
    return {
      file: optimizedFile,
      optimized: true,
      originalWidth: dimensions.width,
      originalHeight: dimensions.height,
      width: encoded.width,
      height: encoded.height,
      originalSize: file.size,
    };
  } catch (error) {
    if (error instanceof Error && /浏览器|自动优化/.test(error.message)) throw error;
    throw new Error("图片自动优化失败，请使用最新版 Chrome 或 Edge，或手动缩小图片后重试。", { cause: error });
  } finally {
    bitmap?.close?.();
  }
}
