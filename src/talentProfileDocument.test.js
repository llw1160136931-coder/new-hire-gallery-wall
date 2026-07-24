import test from "node:test";
import assert from "node:assert/strict";
import {
  MAX_TALENT_PROFILE_AVATAR_BYTES,
  buildPersonalizedTalentProfileBlob,
  buildTalentProfileCsp,
  embedTalentProfileAvatar,
  fetchTalentProfileAvatarDataUrl,
  injectTalentProfileCsp,
  isSafeTalentProfileAvatarDataUrl,
  readTalentProfileAvatarResponseBlob,
  talentProfileAvatarBlobToDataUrl,
  validateTalentProfileAvatarBlob,
  validateTalentProfileAvatarBytes,
} from "./talentProfileDocument.js";

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.className = "";
    this.textContent = "";
  }

  append(child) {
    this.children.push(child);
  }

  prepend(child) {
    this.children.unshift(child);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  querySelector(selector) {
    if (selector === 'meta[data-talent-profile-policy="true"]') {
      return this.children.find(
        (child) => child.tagName === "META"
          && child.getAttribute("data-talent-profile-policy") === "true",
      ) ?? null;
    }
    return null;
  }
}

function serializeFakeElement(element) {
  const attributes = new Map(element.attributes);
  if (element.className && !attributes.has("class")) {
    attributes.set("class", element.className);
  }
  const attributeText = [...attributes.entries()]
    .map(([name, value]) => ` ${name}="${value}"`)
    .join("");
  const tagName = element.tagName.toLowerCase();
  if (tagName === "meta" || tagName === "img") {
    return `<${tagName}${attributeText}>`;
  }
  const childHtml = element.children.map(serializeFakeElement).join("");
  return `<${tagName}${attributeText}>${element.textContent}${childHtml}</${tagName}>`;
}

function fakeProfileDocument({ avatarCount = 1, tagName = "HTML", hasHead = true } = {}) {
  const avatarContainers = Array.from(
    { length: avatarCount },
    () => new FakeElement("div"),
  );
  const head = hasHead ? new FakeElement("head") : null;
  const documentElement = {
    tagName,
    get outerHTML() {
      const avatar = avatarContainers[0]?.children[0];
      const avatarHtml = avatar ? serializeFakeElement(avatar) : "姓";
      const headHtml = head ? head.children.map(serializeFakeElement).join("") : "";
      return `<html><head>${headHtml}</head><body><div class="avatar-circle">${avatarHtml}</div></body></html>`;
    },
  };

  return {
    avatarContainers,
    document: {
      documentElement,
      head,
      createElement: (elementName) => new FakeElement(elementName),
      querySelectorAll: (selector) => (
        selector === ".profile-section .avatar-area > .avatar-circle"
          ? avatarContainers
          : []
      ),
    },
  };
}

function pngBytes(width = 1, height = 1) {
  const bytes = new Uint8Array(24);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  bytes.set([0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52], 8);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return bytes;
}

test("系统头像仅接受非空且不超过 5MB 的常见栅格图片", () => {
  assert.equal(
    validateTalentProfileAvatarBlob(new Blob(["png"], { type: "image/png" })),
    "image/png",
  );
  assert.throws(
    () => validateTalentProfileAvatarBlob(new Blob([], { type: "image/png" })),
    /为空/,
  );
  assert.throws(
    () => validateTalentProfileAvatarBlob(new Blob(["svg"], { type: "image/svg+xml" })),
    /不是受支持/,
  );
  assert.throws(
    () => validateTalentProfileAvatarBlob(
      new Blob([new Uint8Array(MAX_TALENT_PROFILE_AVATAR_BYTES + 1)], { type: "image/jpeg" }),
    ),
    /超过 5MB/,
  );
});

test("头像 Blob 会转换为受限的 base64 data URL", async () => {
  const dataUrl = await talentProfileAvatarBlobToDataUrl(
    new Blob([pngBytes()], { type: "image/png" }),
  );

  assert.match(dataUrl, /^data:image\/png;base64,/);
  assert.equal(isSafeTalentProfileAvatarDataUrl(dataUrl), true);
  assert.equal(isSafeTalentProfileAvatarDataUrl("data:image/svg+xml;base64,AAEC"), false);
  assert.equal(isSafeTalentProfileAvatarDataUrl("https://example.com/avatar.png"), false);
});

test("头像文件头、声明类型和像素上限必须一致", () => {
  assert.deepEqual(
    validateTalentProfileAvatarBytes(pngBytes(2048, 2048), "image/png"),
    { width: 2048, height: 2048, format: "PNG" },
  );
  assert.throws(
    () => validateTalentProfileAvatarBytes(pngBytes(), "image/jpeg"),
    /类型与实际内容不一致/,
  );
  assert.throws(
    () => validateTalentProfileAvatarBytes(pngBytes(8193, 100), "image/png"),
    /分辨率过高/,
  );
  assert.throws(
    () => validateTalentProfileAvatarBytes(new Uint8Array([0, 1, 2]), "image/png"),
    /不是有效/,
  );
});

test("头像读取不携带凭据并禁止缓存和来源头", async () => {
  let capturedUrl = "";
  let capturedOptions = null;
  const dataUrl = await fetchTalentProfileAvatarDataUrl("/media/avatars/student.png", {
    fetchImpl: async (url, options) => {
      capturedUrl = url;
      capturedOptions = options;
      return {
        ok: true,
        headers: {
          get: (name) => (name === "Content-Type" ? "image/png" : null),
        },
        body: new Blob([pngBytes()], { type: "image/png" }).stream(),
      };
    },
  });

  assert.equal(capturedUrl, "/media/avatars/student.png");
  assert.deepEqual(capturedOptions, {
    cache: "no-store",
    credentials: "omit",
    referrerPolicy: "no-referrer",
  });
  assert.match(dataUrl, /^data:image\/png;base64,/);
});

test("头像网络失败不会伪造成有效图片", async () => {
  await assert.rejects(
    fetchTalentProfileAvatarDataUrl("/media/missing.png", {
      fetchImpl: async () => ({ ok: false }),
    }),
    /读取失败/,
  );
});

test("头像声明长度超过 5MB 时会在读取响应前取消", async () => {
  let cancelled = false;
  let blobRead = false;
  const response = {
    headers: {
      get: (name) => (
        name === "Content-Length"
          ? String(MAX_TALENT_PROFILE_AVATAR_BYTES + 1)
          : "image/png"
      ),
    },
    body: {
      cancel: async () => {
        cancelled = true;
      },
    },
    blob: async () => {
      blobRead = true;
      return new Blob([pngBytes()], { type: "image/png" });
    },
  };

  await assert.rejects(
    readTalentProfileAvatarResponseBlob(response),
    /超过 5MB/,
  );
  assert.equal(cancelled, true);
  assert.equal(blobRead, false);
});

test("浏览器不支持流式读取时失败关闭且不会完整缓冲头像", async () => {
  let blobRead = false;
  const response = {
    headers: {
      get: (name) => (name === "Content-Type" ? "image/png" : null),
    },
    body: null,
    blob: async () => {
      blobRead = true;
      return new Blob([pngBytes()], { type: "image/png" });
    },
  };

  await assert.rejects(
    readTalentProfileAvatarResponseBlob(response),
    /无法安全读取/,
  );
  assert.equal(blobRead, false);
});

test("头像流在实际读取超过 5MB 时会立即中止", async () => {
  let readCount = 0;
  let cancelled = false;
  let released = false;
  const reader = {
    read: async () => {
      readCount += 1;
      if (readCount === 1) {
        return {
          done: false,
          value: new Uint8Array(MAX_TALENT_PROFILE_AVATAR_BYTES),
        };
      }
      return { done: false, value: new Uint8Array(1) };
    },
    cancel: async () => {
      cancelled = true;
    },
    releaseLock: () => {
      released = true;
    },
  };
  const response = {
    headers: {
      get: (name) => (name === "Content-Type" ? "image/png" : null),
    },
    body: {
      getReader: () => reader,
    },
  };

  await assert.rejects(
    readTalentProfileAvatarResponseBlob(response),
    /超过 5MB/,
  );
  assert.equal(readCount, 2);
  assert.equal(cancelled, true);
  assert.equal(released, true);
});

test("唯一头像占位会被安全图片替换并注入固定裁切样式", () => {
  const { document, avatarContainers } = fakeProfileDocument();
  const result = embedTalentProfileAvatar(
    document,
    "data:image/png;base64,AAEC",
    "莫子淳的个人头像",
  );

  assert.deepEqual(result, { avatarApplied: true, fallbackReason: "" });
  assert.equal(avatarContainers[0].children.length, 1);
  assert.equal(avatarContainers[0].children[0].tagName, "IMG");
  assert.equal(avatarContainers[0].children[0].className, "talent-profile-avatar");
  assert.equal(
    avatarContainers[0].children[0].getAttribute("src"),
    "data:image/png;base64,AAEC",
  );
  assert.equal(
    avatarContainers[0].children[0].getAttribute("alt"),
    "莫子淳的个人头像",
  );
  assert.match(document.head.children[0].textContent, /object-fit: cover/);
});

test("头像占位缺失、多处或数据不安全时保留原文", () => {
  for (const avatarCount of [0, 2]) {
    const { document, avatarContainers } = fakeProfileDocument({ avatarCount });
    const result = embedTalentProfileAvatar(
      document,
      "data:image/png;base64,AAEC",
      "个人头像",
    );

    assert.equal(result.avatarApplied, false);
    assert.match(result.fallbackReason, /无法唯一识别/);
    assert.equal(avatarContainers.every((container) => container.children.length === 0), true);
    assert.equal(document.head.children.length, 0);
  }

  const { document } = fakeProfileDocument();
  const unsafe = embedTalentProfileAvatar(
    document,
    "data:image/svg+xml;base64,AAEC",
    "个人头像",
  );
  assert.equal(unsafe.avatarApplied, false);
  assert.match(unsafe.fallbackReason, /不安全/);
});

test("CSP 仅在嵌入头像时开放 data 图片，不开放网络图片", () => {
  const withoutAvatar = buildTalentProfileCsp(false);
  const withAvatar = buildTalentProfileCsp(true);

  assert.match(withoutAvatar, /img-src 'none'/);
  assert.match(withAvatar, /img-src data:/);
  assert.doesNotMatch(withAvatar, /img-src \*/);
  assert.doesNotMatch(withAvatar, /img-src https:/);
  assert.match(
    withAvatar,
    /https:\/\/cdn\.jsdelivr\.net\/npm\/chart\.js@4\.4\.1\/dist\/chart\.umd\.min\.js/,
  );
});

test("注入的 CSP 可回读校验", () => {
  const { document } = fakeProfileDocument();

  injectTalentProfileCsp(document, true);

  const cspMeta = document.head.children[0];
  assert.equal(cspMeta.tagName, "META");
  assert.equal(cspMeta.getAttribute("http-equiv"), "Content-Security-Policy");
  assert.match(cspMeta.getAttribute("content"), /img-src data:/);
});

test("预览和下载可共用同一个个性化 Blob 构建器", async () => {
  const fake = fakeProfileDocument();
  const result = await buildPersonalizedTalentProfileBlob(
    new Blob(["<!doctype html><html><head></head><body>原始报告</body></html>"]),
    {
      avatarDataUrl: "data:image/png;base64,AAEC",
      avatarAlt: "莫子淳的个人头像",
      parseDocument: () => fake.document,
    },
  );

  assert.equal(result.avatarApplied, true);
  assert.equal(result.fallbackReason, "");
  assert.equal(result.blob.type, "text/html;charset=utf-8");
  const outputHtml = await result.blob.text();
  assert.match(outputHtml, /^<!DOCTYPE html>/);
  assert.match(outputHtml, /talent-profile-avatar/);
  assert.match(outputHtml, /data-talent-profile-policy="true"/);
  assert.match(outputHtml, /img-src data:/);
  assert.match(outputHtml, /object-fit: cover/);
  assert.match(
    fake.document.head.children[0].getAttribute("content"),
    /img-src data:/,
  );
});

test("空报告或无效文档会失败关闭", async () => {
  await assert.rejects(
    buildPersonalizedTalentProfileBlob(new Blob(["   "])),
    /文件为空/,
  );
  await assert.rejects(
    buildPersonalizedTalentProfileBlob(
      new Blob(["<html></html>"]),
      { parseDocument: () => fakeProfileDocument({ hasHead: false }).document },
    ),
    /安全处理失败/,
  );
});
