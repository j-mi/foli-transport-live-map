import { StarIcon } from './icons'

interface Props {
  pressed: boolean
  onToggle: () => void
  /** What is being saved, for the accessible label, e.g. "line 14" or "Kauppatori". */
  subject: string
  showText?: boolean
}

export function FavouriteButton({ pressed, onToggle, subject, showText = false }: Props) {
  const label = pressed ? `Remove ${subject} from favourites` : `Save ${subject}`
  return (
    <button
      type="button"
      className={`favourite-button${pressed ? ' is-on' : ''}${showText ? ' has-text' : ''}`}
      aria-pressed={pressed}
      aria-label={showText ? undefined : label}
      title={label}
      onClick={(event) => {
        event.stopPropagation()
        onToggle()
      }}
    >
      <StarIcon filled={pressed} />
      {showText && <span>{pressed ? 'Remove from favourites' : 'Save to favourites'}</span>}
    </button>
  )
}
