import { isValidElement, type ReactNode } from 'react'

/**
 * Menerjemahkan pola `asChild` (Radix) ke prop `render` milik Base UI.
 *
 * Base UI tidak punya `asChild`: elemen tujuan diberikan lewat `render`, lalu
 * props dan children komponen dipindahkan ke elemen itu. Helper ini membuat
 * API lama tetap bekerja sehingga pemanggil tidak perlu diubah satu per satu.
 *
 * Tipe `render` dibiarkan generik karena tiap primitif Base UI punya tipe
 * render sendiri; elemen React selalu sah untuk semuanya.
 */
export function asChildProps<R>(
  asChild: boolean | undefined,
  children: ReactNode,
  render: R,
): { render: R; children: ReactNode } {
  if (!asChild || !isValidElement(children)) return { render, children }
  const element = children as { props: { children?: ReactNode } }
  return { render: children as unknown as R, children: element.props.children }
}
