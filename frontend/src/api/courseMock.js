/** @typedef {import('./types.js').Course} Course */
/** @typedef {import('./types.js').CreateCoursePayload} CreateCoursePayload */
/** @typedef {import('./types.js').UpdateCoursePayload} UpdateCoursePayload */

import { isValidCourseDate } from '../utils/courseDates.js'

const COURSES_STORAGE_KEY = 'display-wall-courses'

function createSeedCourses() {
  return [
    { id: 1, title: '创意绘画入门', date: '2026-07-07' },
    { id: 2, title: '水彩技法课', date: '2026-07-07' },
    { id: 3, title: '摄影基础', date: '2026-07-10' },
    { id: 4, title: '手工陶艺体验', date: '2026-07-15' },
    { id: 5, title: '数字艺术创作', date: '2026-08-01' },
    { id: 6, title: '作品展筹备会', date: '2026-08-15' },
  ]
}

/** @returns {Course[]} */
function loadCourses() {
  try {
    const stored = sessionStorage.getItem(COURSES_STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch {
    /* ignore */
  }
  const seed = createSeedCourses()
  saveCourses(seed)
  return seed
}

/** @param {Course[]} courses */
function saveCourses(courses) {
  sessionStorage.setItem(COURSES_STORAGE_KEY, JSON.stringify(courses))
}

function delay(ms = 200) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

let nextCourseId = Math.max(...loadCourses().map((c) => c.id), 0) + 1

/** @returns {Promise<Course[]>} */
export async function getCourses() {
  await delay()
  return loadCourses().sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id)
}

/** @param {string} date @returns {Promise<Course[]>} */
export async function getCoursesByDate(date) {
  await delay()
  return loadCourses()
    .filter((c) => c.date === date)
    .sort((a, b) => a.id - b.id)
}

/** @param {CreateCoursePayload} payload @returns {Promise<Course>} */
export async function createCourse(payload) {
  await delay(200)
  if (!isValidCourseDate(payload.date)) {
    throw new Error('日期须在 7 月至 8 月末之间')
  }
  const courses = loadCourses()
  /** @type {Course} */
  const course = {
    id: nextCourseId++,
    title: payload.title.trim(),
    date: payload.date,
  }
  courses.push(course)
  saveCourses(courses)
  return course
}

/** @param {number} id @param {UpdateCoursePayload} payload @returns {Promise<Course>} */
export async function updateCourse(id, payload) {
  await delay(200)
  const courses = loadCourses()
  const course = courses.find((c) => c.id === id)
  if (!course) throw new Error('课程不存在')

  if (payload.title != null) course.title = payload.title.trim()
  if (payload.date != null) {
    if (!isValidCourseDate(payload.date)) {
      throw new Error('日期须在 7 月至 8 月末之间')
    }
    course.date = payload.date
  }

  saveCourses(courses)
  return course
}

/** @param {number} id */
export async function deleteCourse(id) {
  await delay(150)
  const courses = loadCourses()
  const index = courses.findIndex((c) => c.id === id)
  if (index === -1) throw new Error('课程不存在')
  courses.splice(index, 1)
  saveCourses(courses)
}
