const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001/api";

const ACCESS_TOKEN_KEY = "newHireGallery.accessToken";
const REFRESH_TOKEN_KEY = "newHireGallery.refreshToken";

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export function getStoredTokens() {
  return {
    access: localStorage.getItem(ACCESS_TOKEN_KEY),
    refresh: localStorage.getItem(REFRESH_TOKEN_KEY),
  };
}

export function storeTokens(tokens) {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function parseResponse(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function buildErrorMessage(payload, fallback) {
  if (!payload || typeof payload === "string") {
    return payload || fallback;
  }

  if (payload.detail) {
    return payload.detail;
  }

  const firstKey = Object.keys(payload)[0];
  const firstValue = payload[firstKey];
  if (Array.isArray(firstValue)) {
    return `${firstKey}: ${firstValue.join("，")}`;
  }

  if (typeof firstValue === "string") {
    return `${firstKey}: ${firstValue}`;
  }

  return fallback;
}

async function refreshAccessToken() {
  const { refresh } = getStoredTokens();
  if (!refresh) {
    return null;
  }

  const response = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });

  const payload = await parseResponse(response);
  if (!response.ok || !payload?.access) {
    clearTokens();
    return null;
  }

  const nextTokens = { access: payload.access, refresh: payload.refresh ?? refresh };
  storeTokens(nextTokens);
  return nextTokens.access;
}

export async function apiRequest(path, options = {}) {
  const { auth = true, body, headers, retry = true, ...fetchOptions } = options;
  const token = getStoredTokens().access;
  const isFormData = body instanceof FormData;
  const requestHeaders = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...headers,
  };

  if (auth && token) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...fetchOptions,
    headers: requestHeaders,
    body: isFormData || typeof body === "string" ? body : body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401 && auth && retry) {
    const nextAccess = await refreshAccessToken();
    if (nextAccess) {
      return apiRequest(path, { ...options, retry: false });
    }
  }

  const payload = await parseResponse(response);
  if (!response.ok) {
    throw new ApiError(buildErrorMessage(payload, "请求失败，请稍后再试"), response.status, payload);
  }

  return payload;
}

export async function apiFileRequest(path, options = {}) {
  const { auth = true, headers, retry = true, ...fetchOptions } = options;
  const token = getStoredTokens().access;
  const requestHeaders = { ...headers };
  if (auth && token) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...fetchOptions,
    headers: requestHeaders,
  });

  if (response.status === 401 && auth && retry) {
    const nextAccess = await refreshAccessToken();
    if (nextAccess) {
      return apiFileRequest(path, { ...options, retry: false });
    }
  }

  if (!response.ok) {
    const payload = await parseResponse(response);
    throw new ApiError(buildErrorMessage(payload, "文件读取失败，请稍后再试"), response.status, payload);
  }

  return {
    blob: await response.blob(),
    contentType: response.headers.get("Content-Type") || "application/octet-stream",
  };
}

export async function login(username, password) {
  const tokens = await apiRequest("/auth/token/", {
    method: "POST",
    auth: false,
    body: { username, password },
  });
  storeTokens(tokens);
  return tokens;
}

export const api = {
  me: () => apiRequest("/me/"),
  currentCamp: () => apiRequest("/camps/current/", { auth: false }),
  updateMe: (profile) => apiRequest("/me/", { method: "PATCH", body: profile }),
  attendanceToday: () => apiRequest("/attendance/today/"),
  attendanceCheckIn: (code) => apiRequest("/attendance/check-in/", { method: "POST", body: { code } }),
  adminAttendance: (date) => apiRequest(`/attendance/admin/overview/${date ? `?date=${encodeURIComponent(date)}` : ""}`),
  generateAttendance: () => apiRequest("/attendance/admin/generate/", { method: "POST", body: {} }),
  makeupAttendance: (payload) => apiRequest("/attendance/admin/makeups/", { method: "POST", body: payload }),
  revokeAttendanceMakeup: (recordId, reason) =>
    apiRequest(`/attendance/admin/makeups/${recordId}/revoke/`, { method: "POST", body: { reason } }),
  courses: (date) => apiRequest(date ? `/courses/?date=${date}` : "/courses/"),
  uploadCourseMaterials: (id, formData) =>
    apiRequest(`/courses/${id}/materials/`, { method: "POST", body: formData }),
  deleteCourseMindMap: (id) => apiRequest(`/courses/${id}/mind-map/`, { method: "DELETE" }),
  courseMindMapFile: (id) => apiFileRequest(`/courses/${id}/mind-map-file/`),
  deleteCourseResource: (id) => apiRequest(`/course-resources/${id}/`, { method: "DELETE" }),
  courseResourceFile: (id) => apiFileRequest(`/course-resources/${id}/file/`),
  works: (type) => apiRequest(type && type !== "all" ? `/works/?type=${type}` : "/works/"),
  work: (id) => apiRequest(`/works/${id}/`),
  workFile: (id) => apiFileRequest(`/works/${id}/file/`),
  myWorks: () => apiRequest("/works/my/"),
  pendingWorks: (filters = {}) => {
    const query = new URLSearchParams();
    if (filters.type && filters.type !== "all") query.set("type", filters.type);
    if (filters.mediaType && filters.mediaType !== "all") query.set("media_type", filters.mediaType);
    if (filters.author) query.set("author", filters.author);
    if (filters.ordering) query.set("ordering", filters.ordering);
    const suffix = query.toString();
    return apiRequest(`/works/pending/${suffix ? `?${suffix}` : ""}`);
  },
  reviewLogs: () => apiRequest("/works/review-logs/"),
  bulkReview: (payload) => apiRequest("/works/bulk-review/", { method: "POST", body: payload }),
  leaderboard: () => apiRequest("/leaderboard/"),
  popularTags: () => apiRequest("/tags/popular/", { auth: false }),
  search: (keyword) => apiRequest(`/search/?q=${encodeURIComponent(keyword)}`),
  initUpload: (payload) => apiRequest("/uploads/init/", { method: "POST", body: payload }),
  uploadChunk: (uploadId, formData) => apiRequest(`/uploads/${uploadId}/chunk/`, { method: "POST", body: formData }),
  completeUpload: (uploadId) => apiRequest(`/uploads/${uploadId}/complete/`, { method: "POST" }),
  createWork: (work) => apiRequest("/works/", { method: "POST", body: work }),
  updateWork: (id, work) => apiRequest(`/works/${id}/`, { method: "PATCH", body: work }),
  deleteWork: (id) => apiRequest(`/works/${id}/`, { method: "DELETE" }),
  likeWork: (id) => apiRequest(`/works/${id}/like/`, { method: "POST" }),
  voteWork: (id) => apiRequest(`/works/${id}/vote/`, { method: "POST" }),
  approveWork: (id) => apiRequest(`/works/${id}/approve/`, { method: "POST" }),
  classifyWork: (id, workType) =>
    apiRequest(`/works/${id}/classification/`, { method: "PATCH", body: { work_type: workType } }),
  rejectWork: (id, rejectReason) =>
    apiRequest(`/works/${id}/reject/`, { method: "POST", body: { reject_reason: rejectReason } }),
};
