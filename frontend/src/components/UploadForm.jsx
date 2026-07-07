import { useRef, useState } from 'react'

export default function UploadForm({ onSubmit, onCancel }) {
  const [content, setContent] = useState('')
  const [images, setImages] = useState(/** @type {{ file: File; preview: string }[]} */ ([]))
  const [submitting, setSubmitting] = useState(false)
  const fileRef = useRef(null)

  function handleFileChange(e) {
    const files = Array.from(e.target.files || [])
    const newImages = files.map((file) => ({
      file,
      preview: URL.createObjectURL(file),
    }))
    setImages((prev) => [...prev, ...newImages])
    e.target.value = ''
  }

  function removeImage(index) {
    setImages((prev) => {
      const next = [...prev]
      URL.revokeObjectURL(next[index].preview)
      next.splice(index, 1)
      return next
    })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!content.trim()) return
    if (images.length === 0) return

    setSubmitting(true)
    try {
      await onSubmit({
        content: content.trim(),
        images: images.map((img) => img.file),
      })
      images.forEach((img) => URL.revokeObjectURL(img.preview))
      setContent('')
      setImages([])
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">文字内容</label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          placeholder="写下你的作品描述…"
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium text-gray-700">图片（可多选）</label>
        <div className="flex flex-wrap gap-2">
          {images.map((img, i) => (
            <div key={img.preview} className="relative h-20 w-20">
              <img src={img.preview} alt="" className="h-full w-full rounded-lg object-cover" />
              <button
                type="button"
                onClick={() => removeImage(i)}
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-gray-800 text-xs text-white"
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex h-20 w-20 items-center justify-center rounded-lg border-2 border-dashed border-gray-300 text-gray-400 transition-colors hover:border-blue-400 hover:text-blue-400"
          >
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-lg border border-gray-200 py-2.5 text-sm text-gray-600 transition-colors hover:bg-gray-50"
        >
          取消
        </button>
        <button
          type="submit"
          disabled={submitting || !content.trim() || images.length === 0}
          className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? '提交中…' : '提交投稿'}
        </button>
      </div>
    </form>
  )
}
