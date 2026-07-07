import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRankedWorks } from '../api/client'

/** @typedef {import('../api/types.js').RankPeriod} RankPeriod */

const PERIOD_OPTIONS = [
  { value: 'today', label: '今日' },
  { value: 'total', label: '总计' },
]

const RANK_STYLES = {
  1: 'bg-amber-400 text-white',
  2: 'bg-gray-300 text-gray-700',
  3: 'bg-amber-600 text-white',
}

function getLikeCount(work, period) {
  return period === 'today' ? (work.todayLikeCount ?? 0) : work.likeCount
}

export default function Rank() {
  const navigate = useNavigate()
  const [period, setPeriod] = useState(/** @type {RankPeriod} */ ('today'))
  const [works, setWorks] = useState(/** @type {import('../api/types.js').Work[]} */ ([]))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getRankedWorks(period)
      .then(setWorks)
      .finally(() => setLoading(false))
  }, [period])

  return (
    <div className="mx-auto max-w-lg px-3 pt-4">
      <header className="mb-4">
        <h1 className="text-xl font-bold text-gray-900">排行榜</h1>
        <p className="mt-1 text-sm text-gray-400">按点赞数排序展示作品</p>
      </header>

      <div className="mb-4 flex rounded-lg bg-gray-100 p-1">
        {PERIOD_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setPeriod(/** @type {RankPeriod} */ (opt.value))}
            className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
              period === opt.value
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex animate-pulse gap-3 rounded-xl bg-white p-3 shadow-sm">
              <div className="h-8 w-8 rounded-full bg-gray-200" />
              <div className="h-20 w-20 rounded-lg bg-gray-200" />
              <div className="flex-1 space-y-2 py-1">
                <div className="h-3 rounded bg-gray-200" />
                <div className="h-3 w-1/2 rounded bg-gray-200" />
              </div>
            </div>
          ))}
        </div>
      ) : works.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-gray-400">
          <p className="text-sm">暂无排行数据</p>
        </div>
      ) : (
        <div className="space-y-3">
          {works.map((work, index) => {
            const rank = index + 1
            const likes = getLikeCount(work, period)
            const rankStyle = RANK_STYLES[rank] || 'bg-gray-100 text-gray-600'

            return (
              <button
                key={work.id}
                type="button"
                onClick={() => navigate(`/works/${work.id}`)}
                className="flex w-full items-center gap-3 rounded-xl bg-white p-3 text-left shadow-sm transition-shadow hover:shadow-md"
              >
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${rankStyle}`}
                >
                  {rank}
                </span>
                {work.images[0] && (
                  <img
                    src={work.images[0]}
                    alt=""
                    className="h-20 w-20 shrink-0 rounded-lg object-cover"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-sm text-gray-700">{work.content}</p>
                  <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-400">
                    <span>{work.authorName}</span>
                    <span className="flex items-center gap-0.5 text-red-400">
                      <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
                      </svg>
                      {likes}
                    </span>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
