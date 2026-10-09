/** Slug из названия: «Acme Corp» → `acme-corp`. Кириллица не транслитерируется — её проще вписать руками. */
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
}
