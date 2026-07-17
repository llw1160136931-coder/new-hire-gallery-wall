import test from "node:test";
import assert from "node:assert/strict";
import {
  calculateMindMapResize,
  canAutoOptimizeCourseMindMap,
  courseMindMapWebpName,
  parseImageDimensions,
} from "./courseMindMapImage.js";

test("超高分辨率图片会等比例缩小到约 2000 万像素", () => {
  const result = calculateMindMapResize(14664, 8504);

  assert.equal(result.resized, true);
  assert.ok(result.width * result.height <= 20_000_000);
  assert.ok(Math.abs((result.width / result.height) - (14664 / 8504)) < 0.001);
});

test("普通图片保持原始尺寸", () => {
  const result = calculateMindMapResize(2400, 1600);

  assert.deepEqual(result, {
    width: 2400,
    height: 1600,
    scale: 1,
    resized: false,
  });
});

test("极端长图的最长边不会超过 8192 像素", () => {
  const result = calculateMindMapResize(3000, 30000);

  assert.equal(result.height, 8192);
  assert.ok(result.width * result.height <= 20_000_000);
});

test("用户当前图片在自动优化安全范围内，异常巨图会被拒绝", () => {
  assert.equal(canAutoOptimizeCourseMindMap(14664, 8504), true);
  assert.equal(canAutoOptimizeCourseMindMap(24001, 1000), false);
  assert.equal(canAutoOptimizeCourseMindMap(20000, 8000), false);
});

test("优化后的文件名统一使用 WebP 扩展名", () => {
  assert.equal(courseMindMapWebpName("培训思维导图.png"), "培训思维导图-已优化.webp");
  assert.equal(courseMindMapWebpName("海报"), "海报-已优化.webp");
});

test("可以从 PNG 文件头读取宽高", () => {
  const bytes = new Uint8Array(24);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  bytes.set([0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52], 8);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, 14664);
  view.setUint32(20, 8504);

  assert.deepEqual(parseImageDimensions(bytes), { width: 14664, height: 8504, format: "PNG" });
});

test("可以从 JPEG 文件头读取宽高", () => {
  const bytes = new Uint8Array([
    0xff, 0xd8, 0xff, 0xc0, 0x00, 0x0b, 0x08,
    0x21, 0x38, 0x39, 0x48, 0x03, 0x01, 0x11, 0x00,
  ]);

  assert.deepEqual(parseImageDimensions(bytes), { width: 14664, height: 8504, format: "JPEG" });
});

test("可以从 WebP VP8X 文件头读取宽高", () => {
  const bytes = new Uint8Array(30);
  bytes.set([0x52, 0x49, 0x46, 0x46, 0x16, 0x00, 0x00, 0x00]);
  bytes.set([0x57, 0x45, 0x42, 0x50, 0x56, 0x50, 0x38, 0x58], 8);
  bytes.set([0x0a, 0x00, 0x00, 0x00], 16);
  bytes.set([0x47, 0x39, 0x00, 0x37, 0x21, 0x00], 24);

  assert.deepEqual(parseImageDimensions(bytes), { width: 14664, height: 8504, format: "WEBP" });
});