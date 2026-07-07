import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getWorkById, hasLiked, likeWork } from '../api/client'
import { useUser } from '../context/AuthContext'

export default function WorkDetail() {
  const navigate = useNavigate()
  const user = useUser()
  const { id } = useParams()
  const workId = Number(id)

  const [work, setWork] = useState(/** @type {import('../api/types.js').Work | null} */ (null))
  const [loading, setLoading] = useState(true)
  const [liked, setLiked] = useState(false)
  const [liking, setLiking] = useState(false)

  useEffect(() => {
    getWorkById(workId)
      .then((w) => {
        setWork(w)
        setLiked(hasLiked(w.id, user.id))
      })
      .catch(() => navigate('/home', { replace: true }))
      .finally(() => setLoading(false))
  }, [workId, user.id, navigate])

  async function handleLike() {
    if (!work || liked || liking) return
    setLiking(true)
    try {
      const { likeCount } = await likeWork(work.id, user.id)
      setWork({ ...work, likeCount })
      setLiked(true)
    } catch (err) {
      if (err.status === 409) setLiked(true)
    } finally {
      setLiking(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="animate-pulse space-y-4 p-4">
          <div className="h-64 rounded-xl bg-gray-200" />
          <div className="h-4 w-3/4 rounded bg-gray-200" />
          <div className="h-4 w-1/2 rounded bg-gray-200" />
        </div>
      </div>
    )
  }

  if (!work) return null

  return (
    <div className="min-h-screen bg-gray-50 pb-8">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-gray-100 bg-white/90 px-4 py-3 backdrop-blur">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="flex h-8 w-8 items-center justify-center rounded-full text-gray-600 hover:bg-gray-100"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </button>
        <span className="text-sm font-medium text-gray-900">作品详情</span>
      </header>

      <div className="mx-auto max-w-lg">
        <div className="space-y-1">
          {work.images.map((src, i) => (
            <img key={i} src={src} alt="" className="w-full object-cover" />
          ))}
        </div>

        <div className="space-y-4 p-4">
          <p className="whitespace-pre-wrap text-base leading-relaxed text-gray-800">{work.content}</p>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-medium text-blue-600">
                {work.authorName[0]}
              </div>
              <span className="text-sm text-gray-600">{work.authorName}</span>
            </div>

            <button
              type="button"
              onClick={handleLike}
              disabled={liked || liking}
              className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                liked
                  ? 'bg-red-50 text-red-500'
                  : 'bg-gray-100 text-gray-600 hover:bg-red-50 hover:text-red-500'
              }`}
            >
              <svg
                className="h-5 w-5"
                fill={liked ? 'currentColor' : 'none'}
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={liked ? 0 : 1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"
                />
              </svg>
              {work.likeCount}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
