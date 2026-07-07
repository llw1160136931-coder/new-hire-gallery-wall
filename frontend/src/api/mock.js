/** @typedef {import('./types.js').Work} Work */
/** @typedef {import('./types.js').CreateWorkPayload} CreateWorkPayload */
/** @typedef {import('./types.js').RankPeriod} RankPeriod */

import { getUserById } from './userMock.js'

const STORAGE_KEY = 'display-wall-works-v2'
const LIKES_KEY = 'display-wall-likes'
const DAILY_DATE_KEY = 'display-wall-daily-date'

/** @param {number} userId @param {number} workId */
function likeKey(userId, workId) {
  return `${userId}:${workId}`
}

function createSeedWorks() {
  const now = Date.now()
  return [
    {
      id: 1,
      userId: 1,
      authorName: '张三',
      content: 'test111111',
      images: [
        'https://picsum.photos/seed/wall1/400/520',
        'https://picsum.photos/seed/wall1b/400/300',
      ],
      status: 'approved',
      likeCount: 24,
      todayLikeCount: 8,
      createdAt: new Date(now - 86400000 * 3).toISOString(),
    },
    {
      id: 2,
      userId: 1,
      authorName: '张三',
      content: '测试文本',
      images: ['https://picsum.photos/seed/wall2/400/600'],
      status: 'approved',
      likeCount: 18,
      todayLikeCount: 15,
      createdAt: new Date(now - 86400000 * 2).toISOString(),
    },
    {
      id: 3,
      userId: 2,
      authorName: '李四',
      content: '222222222222222222',
      images: [
        'https://picsum.photos/seed/wall3/400/400',
        'https://picsum.photos/seed/wall3b/400/500',
        'https://picsum.photos/seed/wall3c/400/350',
      ],
      status: 'approved',
      likeCount: 42,
      todayLikeCount: 5,
      createdAt: new Date(now - 86400000).toISOString(),
    },
    {
      id: 4,
      userId: 2,
      authorName: '李四',
      content: '333333333333333333',
      images: ['https://picsum.photos/seed/wall4/400/480'],
      status: 'pending',
      likeCount: 0,
      createdAt: new Date(now - 3600000).toISOString(),
    },
    {
      id: 5,
      userId: 1,
      authorName: '张三',
      content: '此投稿未通过审核。内容不符合展示墙规范，请修改后重新提交。',
      images: ['https://picsum.photos/seed/wall5/400/400'],
      status: 'rejected',
      likeCount: 0,
      createdAt: new Date(now - 86400000 * 5).toISOString(),
    },
  ]
}

/** @returns {Work[]} */
function loadWorks() {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY)
    if (stored) {
      const works = JSON.parse(stored)
      return resetDailyLikesIfNeeded(works)
    }
  } catch {
    /* ignore */
  }
  const seed = createSeedWorks()
  saveWorks(seed)
  return seed
}

/** @param {Work[]} works @returns {Work[]} */
function resetDailyLikesIfNeeded(works) {
  const today = new Date().toDateString()
  const storedDate = sessionStorage.getItem(DAILY_DATE_KEY)
  if (storedDate !== today) {
    works.forEach((w) => {
      w.todayLikeCount = 0
    })
    sessionStorage.setItem(DAILY_DATE_KEY, today)
    saveWorks(works)
  } else {
    works.forEach((w) => {
      if (w.todayLikeCount == null) w.todayLikeCount = 0
    })
  }
  return works
}

/** @param {Work[]} works */
function saveWorks(works) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(works))
}

/** @returns {Set<string>} */
function loadLikes() {
  try {
    const stored = localStorage.getItem(LIKES_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed) && parsed.every((k) => typeof k === 'string')) {
        return new Set(parsed)
      }
    }
  } catch {
    /* ignore */
  }
  return new Set()
}

/** @param {Set<string>} likes */
function saveLikes(likes) {
  localStorage.setItem(LIKES_KEY, JSON.stringify([...likes]))
}

function delay(ms = 200) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

let nextId = Math.max(...loadWorks().map((w) => w.id), 0) + 1

/** @returns {Promise<Work[]>} */
export async function getApprovedWorks() {
  await delay()
  return loadWorks()
    .filter((w) => w.status === 'approved')
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
}

/** @param {number} id */
export async function getWorkById(id) {
  await delay()
  const work = loadWorks().find((w) => w.id === id)
  if (!work) throw new Error('作品不存在')
  return work
}

/** @param {number} userId */
export async function getMyWorks(userId) {
  await delay()
  return loadWorks()
    .filter((w) => w.userId === userId)
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
}

/** @param {CreateWorkPayload} payload */
export async function createWork(payload) {
  await delay(300)
  const works = loadWorks()
  const imageUrls = payload.images.map((file) => URL.createObjectURL(file))
  const author = getUserById(payload.userId)
  /** @type {Work} */
  const work = {
    id: nextId++,
    userId: payload.userId,
    authorName: author?.name ?? '未知用户',
    content: payload.content,
    images: imageUrls,
    status: 'pending',
    likeCount: 0,
    todayLikeCount: 0,
    createdAt: new Date().toISOString(),
  }
  works.unshift(work)
  saveWorks(works)
  return work
}

/** @param {number} workId @param {number} userId */
export async function likeWork(workId, userId) {
  await delay(150)
  const likes = loadLikes()
  const key = likeKey(userId, workId)
  if (likes.has(key)) {
    const err = new Error('已经点赞过了')
    err.status = 409
    throw err
  }
  const works = loadWorks()
  const work = works.find((w) => w.id === workId)
  if (!work) throw new Error('作品不存在')
  work.likeCount += 1
  work.todayLikeCount = (work.todayLikeCount ?? 0) + 1
  saveWorks(works)
  likes.add(key)
  saveLikes(likes)
  return { likeCount: work.likeCount }
}

/** @returns {Promise<Work[]>} */
export async function getPendingSubmissions() {
  await delay()
  return loadWorks()
    .filter((w) => w.status === 'pending')
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
}

/** @param {number} id @param {'approved' | 'rejected'} status */
export async function reviewSubmission(id, status) {
  await delay(200)
  const works = loadWorks()
  const work = works.find((w) => w.id === id)
  if (!work) throw new Error('投稿不存在')
  work.status = status
  saveWorks(works)
  return work
}

/** @param {RankPeriod} period @returns {Promise<Work[]>} */
export async function getRankedWorks(period) {
  await delay()
  const works = loadWorks().filter((w) => w.status === 'approved')
  const getCount = (w) => (period === 'today' ? (w.todayLikeCount ?? 0) : w.likeCount)
  return works.sort((a, b) => getCount(b) - getCount(a) || new Date(b.createdAt) - new Date(a.createdAt))
}

/** @param {number} workId @param {number} userId */
export function hasLiked(workId, userId) {
  return loadLikes().has(likeKey(userId, workId))
}
