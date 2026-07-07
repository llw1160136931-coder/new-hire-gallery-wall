import { useEffect, useState } from 'react'
import { getCoursesByDate } from '../api/client'
import { COURSE_DATE_MAX, COURSE_DATE_MIN } from '../api/types'
import {
  formatCourseDateLabel,
  getDefaultCourseDate,
  isValidCourseDate,
  shiftDate,
} from '../utils/courseDates'

export default function CourseSchedule() {
  const [selectedDate, setSelectedDate] = useState(getDefaultCourseDate)
  const [courses, setCourses] = useState(/** @type {import('../api/types.js').Course[]} */ ([]))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getCoursesByDate(selectedDate)
      .then(setCourses)
      .finally(() => setLoading(false))
  }, [selectedDate])

  function goPrev() {
    const prev = shiftDate(selectedDate, -1)
    if (isValidCourseDate(prev)) setSelectedDate(prev)
  }

  function goNext() {
    const next = shiftDate(selectedDate, 1)
    if (isValidCourseDate(next)) setSelectedDate(next)
  }

  const canGoPrev = shiftDate(selectedDate, -1) >= COURSE_DATE_MIN
  const canGoNext = shiftDate(selectedDate, 1) <= COURSE_DATE_MAX

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-900">课程表</h3>
        <span className="text-xs text-gray-400">7月 - 8月</span>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <button
          type="button"
          disabled={!canGoPrev}
          onClick={goPrev}
          className="flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 disabled:opacity-30"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </button>

        <input
          type="date"
          value={selectedDate}
          min={COURSE_DATE_MIN}
          max={COURSE_DATE_MAX}
          onChange={(e) => {
            if (isValidCourseDate(e.target.value)) setSelectedDate(e.target.value)
          }}
          className="flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-700 outline-none focus:border-blue-400"
        />

        <button
          type="button"
          disabled={!canGoNext}
          onClick={goNext}
          className="flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 disabled:opacity-30"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
        </button>
      </div>

      <p className="mb-3 text-sm font-medium text-blue-600">{formatCourseDateLabel(selectedDate)}</p>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-gray-100" />
          ))}
        </div>
      ) : courses.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">当日暂无课程</p>
      ) : (
        <div className="space-y-2">
          {courses.map((course, index) => (
            <div
              key={course.id}
              className="flex items-center gap-3 rounded-lg border border-blue-50 bg-blue-50/50 px-3 py-2.5"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                {index + 1}
              </span>
              <span className="text-sm font-medium text-gray-800">{course.title}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
