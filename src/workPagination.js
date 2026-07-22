export const WORKS_PAGE_SIZE = 8;

function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function buildWorksQuery(filters = {}) {
  const normalized = typeof filters === "string" ? { type: filters } : filters;
  const query = new URLSearchParams();
  const page = positiveInteger(normalized.page, 1);
  const pageSize = positiveInteger(normalized.pageSize, WORKS_PAGE_SIZE);
  const search = String(normalized.search || "").trim();

  if (normalized.type && normalized.type !== "all") {
    query.set("type", normalized.type);
  }
  if (search) {
    query.set("q", search);
  }
  query.set("page", String(page));
  query.set("page_size", String(pageSize));
  return query.toString();
}

export function normalizeWorksPage(payload, requested = {}) {
  const requestedPage = positiveInteger(requested.page, 1);
  const requestedPageSize = positiveInteger(requested.pageSize, WORKS_PAGE_SIZE);

  if (Array.isArray(payload)) {
    return {
      count: payload.length,
      page: 1,
      page_size: Math.max(payload.length, requestedPageSize),
      total_pages: 1,
      next: null,
      previous: null,
      results: payload,
    };
  }

  const results = Array.isArray(payload?.results) ? payload.results : [];
  const count = Math.max(0, Number.parseInt(payload?.count, 10) || 0);
  const pageSize = positiveInteger(payload?.page_size, requestedPageSize);
  const totalPages = positiveInteger(payload?.total_pages, Math.max(1, Math.ceil(count / pageSize)));

  return {
    ...payload,
    count,
    page: positiveInteger(payload?.page, requestedPage),
    page_size: pageSize,
    total_pages: totalPages,
    next: payload?.next || null,
    previous: payload?.previous || null,
    results,
  };
}

export function buildPaginationItems(page, totalPages) {
  const lastPage = positiveInteger(totalPages, 1);
  const currentPage = Math.min(positiveInteger(page, 1), lastPage);
  const pages = [...new Set([
    1,
    lastPage,
    currentPage - 1,
    currentPage,
    currentPage + 1,
  ].filter((value) => value >= 1 && value <= lastPage))].sort((left, right) => left - right);

  const items = [];
  pages.forEach((value, index) => {
    const previous = pages[index - 1];
    if (index > 0 && value - previous > 1) {
      items.push(`ellipsis-${previous}-${value}`);
    }
    items.push(value);
  });
  return items;
}
