import { useEffect, useState } from 'react'
import { getApprovedWorks } from '../api/client'
import WaterfallGrid from '../components/WaterfallGrid'
import WorkCard from '../components/WorkCard'

function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-xl bg-white shadow-sm">
      <div className="aspect-[3/4] animate-pulse bg-gray-200" />
      <div className="space-y-2 p-3">
        <div className="h-3 animate-pulse rounded bg-gray-200" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-gray-200" />
      </div>
    </div>
  )
}

export default function Home() {
  const [works, setWorks] = useState(/** @type {import('../api/types.js').Work[]} */ ([]))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getApprovedWorks()
      .then(setWorks)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="mx-auto max-w-5xl px-3 pt-4">
      <header className="mb-4">
        <h1 className="text-xl font-bold text-gray-900">展示墙</h1>
      </header>

      {loading ? (
        <WaterfallGrid>
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </WaterfallGrid>
      ) : works.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400">
          <svg className="mb-3 h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z" />
          </svg>
          <p className="text-sm">暂无作品，快去投稿吧</p>
        </div>
      ) : (
        <WaterfallGrid>
          {works.map((work) => (
            <WorkCard key={work.id} work={work} />
          ))}
        </WaterfallGrid>
      )}
    </div>
  )
}
