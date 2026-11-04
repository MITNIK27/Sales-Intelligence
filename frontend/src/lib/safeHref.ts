// A link target taken from stored data: only web addresses are made clickable, so a value such as
// "javascript:..." that came from a scraped page or a model is shown as plain text instead.
export function safeHref(url: string | null | undefined): string | null {
  const value = (url ?? "").trim();
  if (!value) return null;
  try {
    const parsed = new globalThis.URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}
