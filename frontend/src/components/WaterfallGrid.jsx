import Masonry from 'react-masonry-css'

const breakpointColumns = {
  default: 4,
  1024: 3,
  640: 2,
}

export default function WaterfallGrid({ children }) {
  return (
    <Masonry
      breakpointCols={breakpointColumns}
      className="flex w-auto gap-3"
      columnClassName="flex flex-col gap-3"
    >
      {children}
    </Masonry>
  )
}
