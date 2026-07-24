import { parseImageDimensions } from "./courseMindMapImage.js";

export const MAX_TALENT_PROFILE_AVATAR_BYTES = 5 * 1024 * 1024;
export const MAX_TALENT_PROFILE_AVATAR_PIXELS = 40_000_000;
export const MAX_TALENT_PROFILE_AVATAR_EDGE = 8192;

const TALENT_PROFILE_AVATAR_SELECTOR = ".profile-section .avatar-area > .avatar-circle";
const TALENT_PROFILE_CSP_MARKER = "data-talent-profile-policy";
const TALENT_PROFILE_AVATAR_STYLE_MARKER = "data-talent-profile-avatar-style";
const SUPPORTED_AVATAR_TYPES = new Set([
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/webp",
]);

const TALENT_PROFILE_AVATAR_STYLE = [
  ".avatar-circle { overflow: hidden; }",
  ".avatar-circle > .talent-profile-avatar {",
  "  width: 100%;",
  "  height: 100%;",
  "  display: block;",
  "  border-radius: 50%;",
  "  object-fit: cover;",
  "  object-position: center;",
  "}",
].join("\n");

export function buildTalentProfileCsp(hasEmbeddedAvatar = false) {
  return [
    "default-src 'none'",
    "script-src 'unsafe-inline' https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
    "style-src 'unsafe-inline'",
    hasEmbeddedAvatar ? "img-src data:" : "img-src 'none'",
    "font-src 'none'",
    "connect-src 'none'",
    "media-src 'none'",
    "object-src 'none'",
    "frame-src 'none'",
    "worker-src 'none'",
    "form-action 'none'",
    "base-uri 'none'",
  ].join("; ");
}

function normalizedAvatarType(value) {
  return String(value || "").split(";", 1)[0].trim().toLowerCase();
}

export function validateTalentProfileAvatarBlob(avatarBlob) {
  if (!avatarBlob || !Number.isFinite(avatarBlob.size) || avatarBlob.size <= 0) {
    throw new Error("系统头像文件为空");
  }
  if (avatarBlob.size > MAX_TALENT_PROFILE_AVATAR_BYTES) {
    throw new Error("系统头像超过 5MB，无法嵌入人才画像");
  }

  const contentType = normalizedAvatarType(avatarBlob.type);
  if (!SUPPORTED_AVATAR_TYPES.has(contentType)) {
    throw new Error("系统头像不是受支持的 JPG、PNG、WebP 或 GIF 图片");
  }
  return contentType;
}

function parseGifDimensions(bytes) {
  if (bytes.length < 10) {
    return null;
  }
  const signature = String.fromCharCode(...bytes.subarray(0, 6));
  if (signature !== "GIF87a" && signature !== "GIF89a") {
    return null;
  }
  return {
    width: bytes[6] | (bytes[7] << 8),
    height: bytes[8] | (bytes[9] << 8),
    format: "GIF",
  };
}

export function validateTalentProfileAvatarBytes(bytes, contentType) {
  const dimensions = parseImageDimensions(bytes) || parseGifDimensions(bytes);
  const expectedTypeByFormat = {
    GIF: "image/gif",
    JPEG: "image/jpeg",
    PNG: "image/png",
    WEBP: "image/webp",
  };
  if (!dimensions?.width || !dimensions?.height) {
    throw new Error("系统头像文件内容不是有效的 JPG、PNG、WebP 或 GIF 图片");
  }
  if (expectedTypeByFormat[dimensions.format] !== contentType) {
    throw new Error("系统头像文件类型与实际内容不一致");
  }
  if (
    dimensions.width > MAX_TALENT_PROFILE_AVATAR_EDGE
    || dimensions.height > MAX_TALENT_PROFILE_AVATAR_EDGE
    || dimensions.width * dimensions.height > MAX_TALENT_PROFILE_AVATAR_PIXELS
  ) {
    throw new Error("系统头像分辨率过高，无法嵌入人才画像");
  }
  return dimensions;
}

export async function talentProfileAvatarBlobToDataUrl(avatarBlob) {
  const contentType = validateTalentProfileAvatarBlob(avatarBlob);
  const bytes = new Uint8Array(await avatarBlob.arrayBuffer());
  validateTalentProfileAvatarBytes(bytes, contentType);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return `data:${contentType};base64,${btoa(binary)}`;
}

async function cancelResponseBody(response) {
  if (typeof response.body?.cancel === "function") {
    try {
      await response.body.cancel();
    } catch {
      // The stream may already be closed; the caller still rejects the avatar.
    }
  }
}

export async function readTalentProfileAvatarResponseBlob(response) {
  const contentLengthHeader = response.headers?.get?.("Content-Length");
  const declaredLength = Number.parseInt(contentLengthHeader || "", 10);
  if (Number.isFinite(declaredLength) && declaredLength > MAX_TALENT_PROFILE_AVATAR_BYTES) {
    await cancelResponseBody(response);
    throw new Error("系统头像超过 5MB，无法嵌入人才画像");
  }

  if (typeof response.body?.getReader !== "function") {
    await cancelResponseBody(response);
    throw new Error("当前浏览器无法安全读取系统头像");
  }

  const reader = response.body.getReader();
  const chunks = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      totalBytes += value.byteLength;
      if (totalBytes > MAX_TALENT_PROFILE_AVATAR_BYTES) {
        try {
          await reader.cancel();
        } catch {
          // The size rejection below must not be hidden by a stream cancellation failure.
        }
        throw new Error("系统头像超过 5MB，无法嵌入人才画像");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  return new Blob(chunks, {
    type: response.headers?.get?.("Content-Type") || "",
  });
}

export async function fetchTalentProfileAvatarDataUrl(
  avatarUrl,
  { fetchImpl = globalThis.fetch } = {},
) {
  if (!avatarUrl) {
    return "";
  }
  if (typeof fetchImpl !== "function") {
    throw new Error("当前环境无法读取系统头像");
  }

  const response = await fetchImpl(avatarUrl, {
    cache: "no-store",
    credentials: "omit",
    referrerPolicy: "no-referrer",
  });
  if (!response.ok) {
    throw new Error("系统头像读取失败");
  }
  return talentProfileAvatarBlobToDataUrl(
    await readTalentProfileAvatarResponseBlob(response),
  );
}

export function isSafeTalentProfileAvatarDataUrl(value) {
  const match = /^data:([^;,]+);base64,([a-z0-9+/]+={0,2})$/i.exec(String(value || ""));
  return Boolean(
    match
    && SUPPORTED_AVATAR_TYPES.has(normalizedAvatarType(match[1]))
    && match[2].length > 0
    && match[2].length % 4 === 0
    && match[2].length <= Math.ceil(MAX_TALENT_PROFILE_AVATAR_BYTES / 3) * 4
  );
}

export function embedTalentProfileAvatar(
  profileDocument,
  avatarDataUrl,
  avatarAlt = "个人头像",
) {
  if (!avatarDataUrl) {
    return { avatarApplied: false, fallbackReason: "" };
  }
  if (!isSafeTalentProfileAvatarDataUrl(avatarDataUrl)) {
    return { avatarApplied: false, fallbackReason: "系统头像数据格式不安全" };
  }

  const avatarContainers = profileDocument.querySelectorAll(TALENT_PROFILE_AVATAR_SELECTOR);
  if (avatarContainers.length !== 1) {
    return { avatarApplied: false, fallbackReason: "画像头像区域无法唯一识别" };
  }

  const avatarImage = profileDocument.createElement("img");
  avatarImage.className = "talent-profile-avatar";
  avatarImage.setAttribute("src", avatarDataUrl);
  avatarImage.setAttribute("alt", avatarAlt || "个人头像");
  avatarImage.setAttribute("draggable", "false");
  avatarContainers[0].replaceChildren(avatarImage);

  const avatarStyle = profileDocument.createElement("style");
  avatarStyle.setAttribute(TALENT_PROFILE_AVATAR_STYLE_MARKER, "true");
  avatarStyle.textContent = TALENT_PROFILE_AVATAR_STYLE;
  profileDocument.head.append(avatarStyle);

  return { avatarApplied: true, fallbackReason: "" };
}

export function injectTalentProfileCsp(profileDocument, hasEmbeddedAvatar) {
  const cspMeta = profileDocument.createElement("meta");
  const content = buildTalentProfileCsp(hasEmbeddedAvatar);
  cspMeta.setAttribute("http-equiv", "Content-Security-Policy");
  cspMeta.setAttribute("content", content);
  cspMeta.setAttribute(TALENT_PROFILE_CSP_MARKER, "true");
  profileDocument.head.prepend(cspMeta);

  const injectedCsp = profileDocument.head.querySelector(
    `meta[${TALENT_PROFILE_CSP_MARKER}="true"]`,
  );
  if (injectedCsp?.getAttribute("content") !== content) {
    throw new Error("人才画像安全策略注入失败");
  }
}

export async function buildPersonalizedTalentProfileBlob(
  fileBlob,
  {
    avatarDataUrl = "",
    avatarAlt = "个人头像",
    parseDocument = (html) => new DOMParser().parseFromString(html, "text/html"),
  } = {},
) {
  const html = await fileBlob.text();
  if (!html.trim()) {
    throw new Error("人才画像文件为空，请联系管理员重新发布");
  }

  const profileDocument = parseDocument(html);
  const documentElement = profileDocument?.documentElement;
  const head = profileDocument?.head;
  if (!documentElement || documentElement.tagName !== "HTML" || !head) {
    throw new Error("人才画像安全处理失败，请联系管理员重新发布");
  }

  const avatarResult = embedTalentProfileAvatar(
    profileDocument,
    avatarDataUrl,
    avatarAlt,
  );
  injectTalentProfileCsp(profileDocument, avatarResult.avatarApplied);

  return {
    blob: new Blob(
      [`<!DOCTYPE html>\n${documentElement.outerHTML}`],
      { type: "text/html;charset=utf-8" },
    ),
    ...avatarResult,
  };
}
