import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPaginationItems,
  buildWorksQuery,
  normalizeWorksPage,
  WORKS_PAGE_SIZE,
} from "./workPagination.js";

test("作品查询包含服务端分页、分类和关键词", () => {
  const query = new URLSearchParams(buildWorksQuery({
    type: "ai",
    page: 3,
    pageSize: WORKS_PAGE_SIZE,
    search: "  数据看板  ",
  }));

  assert.equal(query.get("type"), "ai");
  assert.equal(query.get("page"), "3");
  assert.equal(query.get("page_size"), "8");
  assert.equal(query.get("q"), "数据看板");
});

test("分页响应会保留总数、页数和当前页作品", () => {
  const result = normalizeWorksPage({
    count: 18,
    page: 2,
    page_size: 8,
    total_pages: 3,
    next: "next-url",
    previous: "previous-url",
    results: [{ id: 9 }],
  });

  assert.equal(result.count, 18);
  assert.equal(result.page, 2);
  assert.equal(result.total_pages, 3);
  assert.deepEqual(result.results, [{ id: 9 }]);
});

test("滚动部署期间仍能兼容旧版数组响应", () => {
  const result = normalizeWorksPage([{ id: 1 }, { id: 2 }], { pageSize: 8 });

  assert.equal(result.count, 2);
  assert.equal(result.total_pages, 1);
  assert.deepEqual(result.results, [{ id: 1 }, { id: 2 }]);
});

test("页码只显示首尾和当前页附近并插入省略号", () => {
  assert.deepEqual(buildPaginationItems(5, 10), [1, "ellipsis-1-4", 4, 5, 6, "ellipsis-6-10", 10]);
  assert.deepEqual(buildPaginationItems(1, 2), [1, 2]);
});
