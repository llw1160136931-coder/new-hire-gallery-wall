import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createWork, getMyWorks } from '../api/client'
import { useAuth, useUser } from '../context/AuthContext'
import StatusBadge from '../components/StatusBadge'
import UploadForm from '../components/UploadForm'
import CourseSchedule from '../components/CourseSchedule'

function Toast({ message, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 2500)
    return () => clearTimeout(timer)
  }, [onClose])

  return (
    <div className="fixed left-1/2 top-16 z-50 -translate-x-1/2 rounded-lg bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg">
      {message}
    </div>
  )
}

export default function My() {
  const user = useUser()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [works, setWorks] = useState(/** @type {import('../api/types.js').Work[]} */ ([]))
  const [loading, setLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [toast, setToast] = useState('')

  const loadWorks = useCallback(() => {
    setLoading(true)
    getMyWorks(user.id)
      .then(setWorks)
      .finally(() => setLoading(false))
  }, [user.id])

  useEffect(() => {
    loadWorks()
  }, [loadWorks])

  async function handleUpload(payload) {
    await createWork({ userId: user.id, ...payload })
    setShowUpload(false)
    setToast('投稿成功，等待审核')
    loadWorks()
  }

  return (
    <div className="mx-auto max-w-lg">
      {toast && <Toast message={toast} onClose={() => setToast('')} />}

      <div className="bg-white px-4 py-6">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-2xl font-bold text-blue-600">
            {user.name[0]}
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold text-gray-900">{user.name}</h2>
            <p className="text-sm text-gray-400">ID: {user.id}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
            className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50"
          >
            退出
          </button>
        </div>
      </div>

      <div className="mt-2 bg-white px-4 py-4">
        <CourseSchedule />
      </div>

      <div className="mt-2 bg-white px-4 py-4 pb-28">
        <h3 className="mb-3 text-base font-semibold text-gray-900">我的作品</h3>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <div className="h-16 w-16 animate-pulse rounded-lg bg-gray-200" />
                <div className="flex-1 space-y-2 py-1">
                  <div className="h-3 animate-pulse rounded bg-gray-200" />
                  <div className="h-3 w-1/2 animate-pulse rounded bg-gray-200" />
                </div>
              </div>
            ))}
          </div>
        ) : works.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-400">还没有作品，点击下方按钮上传</p>
        ) : (
          <div className="space-y-3">
            {works.map((work) => (
              <div key={work.id} className="flex gap-3 rounded-lg border border-gray-100 p-2">
                {work.images[0] && (
                  <img src={work.images[0]} alt="" className="h-16 w-16 shrink-0 rounded-lg object-cover" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-gray-700">{work.content}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <StatusBadge status={work.status} />
                    <span className="text-xs text-gray-400">
                      {new Date(work.createdAt).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="fixed bottom-20 left-0 right-0 px-4">
        {showUpload ? (
          <div className="mx-auto max-w-lg rounded-xl bg-white p-4 shadow-xl">
            <h3 className="mb-3 text-base font-semibold text-gray-900">上传作品</h3>
            <UploadForm onSubmit={handleUpload} onCancel={() => setShowUpload(false)} />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowUpload(true)}
            className="mx-auto flex w-full max-w-lg items-center justify-center gap-2 rounded-xl bg-blue-600 py-3.5 text-sm font-medium text-white shadow-lg transition-colors hover:bg-blue-700"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            上传作品
          </button>
        )}
      </div>
    </div>
  )
}
