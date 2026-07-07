/** @typedef {import('./types.js').User} User */

const USERS = [
  { id: 1, name: '张三' },
  { id: 2, name: '李四' },
]

const ADMINS = [
  { id: 1, name: '管理员' },
]

function delay(ms = 150) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** @param {string} name */
export function findUserByName(name) {
  const trimmed = name.trim()
  return USERS.find((u) => u.name === trimmed) ?? null
}

/** @param {string} name */
export function findAdminByName(name) {
  const trimmed = name.trim()
  return ADMINS.find((a) => a.name === trimmed) ?? null
}

/** @param {number} id */
export function getUserById(id) {
  return USERS.find((u) => u.id === id) ?? null
}

/** @returns {User[]} */
export function getAllUsers() {
  return [...USERS]
}

/** @param {string} name @returns {Promise<User>} */
export async function loginUser(name) {
  await delay()
  const user = findUserByName(name)
  if (!user) {
    const err = new Error('用户不存在，请检查昵称')
    err.status = 404
    throw err
  }
  return { ...user }
}

/** @param {string} name @returns {Promise<User>} */
export async function loginAdmin(name) {
  await delay()
  const admin = findAdminByName(name)
  if (!admin) {
    const err = new Error('管理员不存在，请检查名称')
    err.status = 404
    throw err
  }
  return { ...admin }
}

/** @param {number} id @param {string} name */
export function verifyUser(id, name) {
  const user = getUserById(id)
  return user != null && user.name === name
}

/** @param {number} id @param {string} name */
export function verifyAdmin(id, name) {
  const admin = ADMINS.find((a) => a.id === id && a.name === name)
  return admin != null
}
