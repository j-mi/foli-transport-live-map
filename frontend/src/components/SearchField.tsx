import { useId } from 'react'
import { SearchIcon } from './icons'

interface Props {
  label: string
  placeholder: string
  value: string
  onChange: (value: string) => void
}

/** `data-search-input` lets the "/" keyboard shortcut find the active panel's search box. */
export function SearchField({ label, placeholder, value, onChange }: Props) {
  const id = useId()
  return (
    <div className="search-field">
      <label htmlFor={id} className="visually-hidden">
        {label}
      </label>
      <SearchIcon className="search-field__icon" />
      <input
        id={id}
        type="search"
        data-search-input
        placeholder={placeholder}
        value={value}
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && value) {
            event.stopPropagation()
            onChange('')
          }
        }}
      />
    </div>
  )
}
