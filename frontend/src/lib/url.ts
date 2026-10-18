// A company's domain is stored bare ("acme.com") or sometimes as a full address. This gives the
// address to open: https unless one is already given. Anything else is treated as a bare domain,
// so a stray scheme such as "javascript:" can never become a clickable link.
export function websiteUrl(domain: string): string {
  const trimmed = domain.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

// The text to show for a website: the domain without the scheme or a trailing slash.
export function websiteLabel(domain: string): string {
  return domain
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/\/$/, "");
}
