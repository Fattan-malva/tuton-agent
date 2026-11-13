'use client'

import { Input } from '@/components/ui/input'

export function ModelInput({
  id,
  value,
  onChange,
  models,
  placeholder = 'Klik untuk melihat model, ketik untuk mencari',
}: {
  id: string
  value: string
  onChange: (value: string) => void
  models: string[]
  placeholder?: string
}) {
  return (
    <>
      <Input
        id={id}
        list={`${id}-models`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete='off'
      />
      <datalist id={`${id}-models`}>
        {models.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
    </>
  )
}
