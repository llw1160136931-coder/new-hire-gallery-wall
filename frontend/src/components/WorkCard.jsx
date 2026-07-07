import { useNavigate } from 'react-router-dom'

function truncate(text, max = 50) {
  if (text.length <= max) return text
  return text.slice(0, max) + '…'
}

export default function WorkCard({ work }) {
  const navigate = useNavigate()
  const cover = work.images[0]

  return (
    <button
      type="button"
      onClick={() => navigate(`/works/${work.id}`)}
      className="w-full overflow-hidden rounded-xl bg-white text-left shadow-sm transition-shadow hover:shadow-md"
    >
      {cover && (
        <img
          src={cover}
          alt=""
          className="w-full object-cover"
          loading="lazy"
        />
      )}
      <div className="p-3">
        <p className="text-sm text-gray-700 line-clamp-2">{truncate(work.content)}</p>
        <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
          <span>{work.authorName}</span>
          <span className="flex items-center gap-1">
            <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
            </svg>
            {work.likeCount}
          </span>
        </div>
      </div>
    </button>
  )
}
