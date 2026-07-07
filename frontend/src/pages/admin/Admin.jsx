import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createCourse,
  deleteCourse,
  getCourses,
  getPendingSubmissions,
  reviewSubmission,
  updateCourse,
} from '../../api/client'
import { useAuth, useUser } from '../../context/AuthContext'
import CourseForm from '../../components/CourseForm'
import { formatCourseDateLabel } from '../../utils/courseDates'

/** @typedef {import('../../api/types.js').Work} Work */
/** @typedef {import('../../api/types.js').Course} Course */

function SubmissionsPanel() {
  const [submissions, setSubmissions] = useState(/** @type {Work[]} */ ([]))
  const [loading, setLoading] = useState(true)
  const [processingId, setProcessingId] = useState(/** @type {number | null} */ (null))

  const load = useCallback(() => {
    setLoading(true)
    getPendingSubmissions()
      .then(setSubmissions)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleReview(id, status) {
    setProcessingId(id)
    try {
      await reviewSubmission(id, status)
      setSubmissions((prev) => prev.filter((s) => s.id !== id))
    } finally {
      setProcessingId(null)
    }
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="animate-pulse rounded-xl bg-white p-4 shadow-sm">
            <div className="flex gap-3">
              <div className="h-20 w-20 rounded-lg bg-gray-200" />
              <div className="flex-1 space-y-2">
                <div className="h-3 rounded bg-gray-200" />
                <div className="h-3 w-2/3 rounded bg-gray-200" />
              </div>
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (submissions.length === 0) {
    return (
      <div className="flex flex-col items-center py-16 text-gray-400">
        <svg className="mb-3 h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-sm">暂无待审核投稿</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {submissions.map((item) => (
        <div key={item.id} className="rounded-xl bg-white p-4 shadow-sm">
          <div className="flex gap-3">
            {item.images[0] && (
              <img src={item.images[0]} alt="" className="h-20 w-20 shrink-0 rounded-lg object-cover" />
            )}
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm text-gray-700">{item.content}</p>
              <p className="mt-1 text-xs text-gray-400">
                {item.authorName} · {new Date(item.createdAt).toLocaleString('zh-CN')}
              </p>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={processingId === item.id}
              onClick={() => handleReview(item.id, 'rejected')}
              className="flex-1 rounded-lg border border-gray-200 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              拒绝
            </button>
            <button
              type="button"
              disabled={processingId === item.id}
              onClick={() => handleReview(item.id, 'approved')}
              className="flex-1 rounded-lg bg-green-600 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:opacity-50"
            >
              通过
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

function CoursesPanel() {
  const [courses, setCourses] = useState(/** @type {Course[]} */ ([]))
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(/** @type {Course | null} */ (null))
  const [showForm, setShowForm] = useState(false)
  const [deletingId, setDeletingId] = useState(/** @type {number | null} */ (null))

  const load = useCallback(() => {
    setLoading(true)
    getCourses()
      .then(setCourses)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate(payload) {
    await createCourse(payload)
    setShowForm(false)
    load()
  }

  async function handleUpdate(payload) {
    if (!editing) return
    await updateCourse(editing.id, payload)
    setEditing(null)
    load()
  }

  async function handleDelete(id) {
    if (!confirm('确定删除该课程？')) return
    setDeletingId(id)
    try {
      await deleteCourse(id)
      load()
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-500">共 {courses.length} 门课程</p>
        <button
          type="button"
          onClick={() => {
            setEditing(null)
            setShowForm(true)
          }}
          className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          + 添加课程
        </button>
      </div>

      {(showForm || editing) && (
        <div className="mb-4 rounded-xl bg-white p-4 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            {editing ? '编辑课程' : '添加课程'}
          </h3>
          <CourseForm
            course={editing}
            onSubmit={editing ? handleUpdate : handleCreate}
            onCancel={() => {
              setShowForm(false)
              setEditing(null)
            }}
          />
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-white" />
          ))}
        </div>
      ) : courses.length === 0 ? (
        <p className="py-12 text-center text-sm text-gray-400">暂无课程，点击上方按钮添加</p>
      ) : (
        <div className="space-y-2">
          {courses.map((course) => (
            <div
              key={course.id}
              className="flex items-center gap-3 rounded-xl bg-white px-4 py-3 shadow-sm"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-800">{course.title}</p>
                <p className="mt-0.5 text-xs text-gray-400">{formatCourseDateLabel(course.date)}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false)
                  setEditing(course)
                }}
                className="rounded-lg px-2.5 py-1 text-xs text-blue-600 hover:bg-blue-50"
              >
                编辑
              </button>
              <button
                type="button"
                disabled={deletingId === course.id}
                onClick={() => handleDelete(course.id)}
                className="rounded-lg px-2.5 py-1 text-xs text-red-500 hover:bg-red-50 disabled:opacity-50"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Admin() {
  const [tab, setTab] = useState(/** @type {'submissions' | 'courses'} */ ('submissions'))
  const user = useUser()
  const { logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-10 border-b border-gray-100 bg-white">
        <div className="flex items-center gap-3 px-4 py-3">
          <h1 className="text-base font-semibold text-gray-900">管理后台</h1>
          <span className="text-xs text-gray-400">{user.name}</span>
          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
            className="ml-auto rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50"
          >
            退出
          </button>
        </div>

        <div className="flex border-t border-gray-100">
          <button
            type="button"
            onClick={() => setTab('submissions')}
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              tab === 'submissions'
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            投稿审核
          </button>
          <button
            type="button"
            onClick={() => setTab('courses')}
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              tab === 'courses'
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            课程管理
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-lg p-4">
        {tab === 'submissions' ? <SubmissionsPanel /> : <CoursesPanel />}
      </div>
    </div>
  )
}
