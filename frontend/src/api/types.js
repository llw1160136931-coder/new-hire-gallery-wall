/**
 * @typedef {'pending' | 'approved' | 'rejected'} WorkStatus
 */

/**
 * @typedef {'today' | 'total'} RankPeriod
 */

/**
 * @typedef {Object} User
 * @property {number} id
 * @property {string} name
 * @property {string} [avatar]
 */

/**
 * @typedef {Object} Work
 * @property {number} id
 * @property {number} userId
 * @property {string} authorName
 * @property {string} content
 * @property {string[]} images
 * @property {WorkStatus} status
 * @property {number} likeCount
 * @property {number} [todayLikeCount]
 * @property {string} createdAt
 */

/**
 * @typedef {Object} CreateWorkPayload
 * @property {number} userId
 * @property {string} content
 * @property {File[]} images
 */

/**
 * @typedef {Object} Course
 * @property {number} id
 * @property {string} title
 * @property {string} date YYYY-MM-DD，范围 7月-8月末
 */

/**
 * @typedef {Object} CreateCoursePayload
 * @property {string} title
 * @property {string} date
 */

/**
 * @typedef {Object} UpdateCoursePayload
 * @property {string} [title]
 * @property {string} [date]
 */

export const COURSE_DATE_MIN = '2026-07-01'
export const COURSE_DATE_MAX = '2026-08-31'
