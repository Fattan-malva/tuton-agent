declare module 'docx-preview' {
  export function renderAsync(data: any, bodyContainer: HTMLElement, styleContainer?: HTMLElement, userOptions?: any): Promise<any>
  export function renderDocument(document: any, bodyContainer: HTMLElement, styleContainer?: HTMLElement, userOptions?: any): Promise<any>
  export function parseAsync(data: any, userOptions?: any): Promise<any>
  export const defaultOptions: any
}
