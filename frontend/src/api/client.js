/** @typedef {import('./types.js').Work} Work */
/** @typedef {import('./types.js').CreateWorkPayload} CreateWorkPayload */
/** @typedef {import('./types.js').RankPeriod} RankPeriod */
/** @typedef {import('./types.js').Course} Course */
/** @typedef {import('./types.js').CreateCoursePayload} CreateCoursePayload */
/** @typedef {import('./types.js').UpdateCoursePayload} UpdateCoursePayload */

/** @typedef {import('./types.js').User} User */

import axios from 'axios'
import * as mock from './mock.js'
import * as courseMock from './courseMock.js'
import * as userMock from './userMock.js'

const useMock = import.meta.env.VITE_USE_MOCK !== 'false'

const http = axios.create({ baseURL: '/api' })

/** @param {string} name @returns {Promise<User>} */
export async function loginUser(name) {
  if (useMock) return userMock.loginUser(name)
  const { data } = await http.post('/auth/login', { name, role: 'user' })
  return data
}

/** @param {string} name @returns {Promise<User>} */
export async function loginAdmin(name) {
  if (useMock) return userMock.loginAdmin(name)
  const { data } = await http.post('/auth/login', { name, role: 'admin' })
  return data
}

/** @returns {Promise<Work[]>} */
export async function getApprovedWorks() {
  if (useMock) return mock.getApprovedWorks()
  const { data } = await http.get('/works')
  return data
}

/** @param {number} id @returns {Promise<Work>} */
export async function getWorkById(id) {
  if (useMock) return mock.getWorkById(id)
  const { data } = await http.get(`/works/${id}`)
  return data
}

/** @param {number} userId @returns {Promise<Work[]>} */
export async function getMyWorks(userId) {
  if (useMock) return mock.getMyWorks(userId)
  const { data } = await http.get('/works/my', { params: { userId } })
  return data
}

/** @param {CreateWorkPayload} payload @returns {Promise<Work>} */
export async function createWork(payload) {
  if (useMock) return mock.createWork(payload)

  const formData = new FormData()
  formData.append('userId', String(payload.userId))
  formData.append('content', payload.content)
  payload.images.forEach((file) => formData.append('images', file))

  const { data } = await http.post('/works', formData)
  return data
}

/** @param {number} workId @param {number} userId */
export async function likeWork(workId, userId) {
  if (useMock) return mock.likeWork(workId, userId)
  const { data } = await http.post(`/works/${workId}/like`, { userId })
  return data
}

/** @returns {Promise<Work[]>} */
export async function getPendingSubmissions() {
  if (useMock) return mock.getPendingSubmissions()
  const { data } = await http.get('/admin/submissions')
  return data
}

/** @param {number} id @param {'approved' | 'rejected'} status */
export async function reviewSubmission(id, status) {
  if (useMock) return mock.reviewSubmission(id, status)
  const { data } = await http.patch(`/admin/submissions/${id}`, { status })
  return data
}

/** @param {RankPeriod} period @returns {Promise<Work[]>} */
export async function getRankedWorks(period) {
  if (useMock) return mock.getRankedWorks(period)
  const { data } = await http.get('/works/rank', { params: { period } })
  return data
}

/** @param {number} workId @param {number} userId */
export function hasLiked(workId, userId) {
  if (useMock) return mock.hasLiked(workId, userId)
  return false
}

/** @returns {Promise<Course[]>} */
export async function getCourses() {
  if (useMock) return courseMock.getCourses()
  const { data } = await http.get('/courses')
  return data
}

/** @param {string} date @returns {Promise<Course[]>} */
export async function getCoursesByDate(date) {
  if (useMock) return courseMock.getCoursesByDate(date)
  const { data } = await http.get('/courses', { params: { date } })
  return data
}

/** @param {CreateCoursePayload} payload @returns {Promise<Course>} */
export async function createCourse(payload) {
  if (useMock) return courseMock.createCourse(payload)
  const { data } = await http.post('/courses', payload)
  return data
}

/** @param {number} id @param {UpdateCoursePayload} payload @returns {Promise<Course>} */
export async function updateCourse(id, payload) {
  if (useMock) return courseMock.updateCourse(id, payload)
  const { data } = await http.patch(`/courses/${id}`, payload)
  return data
}

/** @param {number} id */
export async function deleteCourse(id) {
  if (useMock) return courseMock.deleteCourse(id)
  await http.delete(`/courses/${id}`)
}
