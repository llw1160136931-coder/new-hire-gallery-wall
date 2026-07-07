import { COURSE_DATE_MAX, COURSE_DATE_MIN } from '../api/types.js'

/** @param {string} date */
export function isValidCourseDate(date) {
  return date >= COURSE_DATE_MIN && date <= COURSE_DATE_MAX
}

/** @returns {string} */
export function getDefaultCourseDate() {
  const today = formatDate(new Date())
  if (isValidCourseDate(today)) return today
  return COURSE_DATE_MIN
}

/** @param {Date} d */
export function formatDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** @param {string} date @param {number} deltaDays */
export function shiftDate(date, deltaDays) {
  const d = new Date(date + 'T00:00:00')
  d.setDate(d.getDate() + deltaDays)
  return formatDate(d)
}

/** @param {string} date */
export function formatCourseDateLabel(date) {
  const d = new Date(date + 'T00:00:00')
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getMonth() + 1}月${d.getDate()}日 周${weekdays[d.getDay()]}`
}
