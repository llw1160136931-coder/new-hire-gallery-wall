import test from "node:test";
import assert from "node:assert/strict";
import { MAX_WORK_HTML_UPLOAD_BYTES, MAX_WORK_IMAGE_COUNT, mergeSelectedWorkFiles } from "./workFileSelection.js";

function image(name, lastModified) {
  return { name, size: 1024, lastModified, type: "image/jpeg" };
}

function pdf(name = "作品.pdf") {
  return { name, size: 2048, lastModified: 1, type: "application/pdf" };
}

test("分两次选择图片时会追加并保留顺序", () => {
  const first = image("第一张.jpg", 1);
  const second = image("第二张.jpg", 2);
  const firstSelection = mergeSelectedWorkFiles({ asset: null, images: [] }, [first]);
  const secondSelection = mergeSelectedWorkFiles(firstSelection, [second]);

  assert.deepEqual(secondSelection.images, [first, second]);
  assert.equal(secondSelection.asset, null);
});

test("再次选择已经添加过的图片不会产生重复项", () => {
  const first = image("第一张.jpg", 1);
  const result = mergeSelectedWorkFiles({ asset: null, images: [first] }, [first]);

  assert.match(result.error, /已经添加过/);
});

test("累计图片超过十张时会拒绝本次追加", () => {
  const currentImages = Array.from({ length: MAX_WORK_IMAGE_COUNT }, (_, index) => image(`${index}.jpg`, index));
  const result = mergeSelectedWorkFiles({ asset: null, images: currentImages }, [image("超出.jpg", 99)]);

  assert.match(result.error, /最多只能上传 10 张/);
});

test("已有图片时不能混入 PDF", () => {
  const result = mergeSelectedWorkFiles({ asset: null, images: [image("图片.jpg", 1)] }, [pdf()]);

  assert.match(result.error, /先移除全部图片/);
});

test("PDF 可以被另一份 PDF 替换", () => {
  const replacement = pdf("新版本.pdf");
  const result = mergeSelectedWorkFiles({ asset: pdf("旧版本.pdf"), images: [] }, [replacement]);

  assert.equal(result.asset, replacement);
  assert.deepEqual(result.images, []);
});

function html(name = "demo.html", size = 4096) {
  return { name, size, lastModified: 2, type: "text/html" };
}

test("可以单独选择 HTML 文件", () => {
  const selected = html();
  const result = mergeSelectedWorkFiles({ asset: null, images: [] }, [selected]);

  assert.equal(result.asset, selected);
  assert.deepEqual(result.images, []);
});

test("HTML 文件超过 20MB 时会被拒绝", () => {
  const result = mergeSelectedWorkFiles(
    { asset: null, images: [] },
    [html("too-large.html", MAX_WORK_HTML_UPLOAD_BYTES + 1)],
  );

  assert.match(result.error, /HTML 文件 20MB 限制/);
});
