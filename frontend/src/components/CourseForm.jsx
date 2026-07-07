import { useEffect, useState } from 'react'
import { COURSE_DATE_MAX, COURSE_DATE_MIN } from '../api/types'

/** @typedef {import('../api/types.js').Course} Course */

/**
 * @param {Object} props
 * @param {Course | null} props.course
 * @param {(payload: { title: string; date: string }) => void | Promise<void>} props.onSubmit
 * @param {() => void} props.onCancel
 */
export default function CourseForm({ course, onSubmit, onCancel }) {
  const [title, setTitle] = useState(course?.title ?? '')
  const [date, setDate] = useState(course?.date ?? '2026-07-07')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setTitle(course?.title ?? '')
    setDate(course?.date ?? '2026-07-07')
  }, [course])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!title.trim()) return
    setSubmitting(true)
    try {
      await onSubmit({ title: title.trim(), date })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">课程标题</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="输入课程名称"
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">日期</label>
        <input
          type="date"
          value={date}
          min={COURSE_DATE_MIN}
          max={COURSE_DATE_MAX}
          onChange={(e) => setDate(e.target.value)}
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
        <p className="mt-1 text-xs text-gray-400">可选范围：7月1日 - 8月31日</p>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-lg border border-gray-200 py-2 text-sm text-gray-600 hover:bg-gray-50"
        >
          取消
        </button>
        <button
          type="submit"
          disabled={submitting || !title.trim()}
          className="flex-1 rounded-lg bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? '保存中…' : course ? '保存修改' : '添加课程'}
        </button>
      </div>
    </form>
  )
}
