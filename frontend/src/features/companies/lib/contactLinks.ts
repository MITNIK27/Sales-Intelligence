import type { ContactChannel } from "@/api/types";

export type ChannelLink = { href: string; label: string };

// Where a contact channel opens when clicked, or null when it is not a link (a phone number, or
// a value that is not a web address). Only http(s) and mailto links are produced, so a stored
// value can never become a script link.
export function channelLink(
  channel: Pick<ContactChannel, "channel_type" | "value">,
): ChannelLink | null {
  const value = channel.value.trim();
  if (!value) return null;
  const type = channel.channel_type.toLowerCase();

  if (type === "email") {
    return /^[^\s@]+@[^\s@]+$/.test(value)
      ? { href: `mailto:${value}`, label: value }
      : null;
  }

  const looksLikeUrl = /^https?:\/\//i.test(value);
  if (type === "linkedin") {
    const href = looksLikeUrl ? value : `https://${value.replace(/^\/+/, "")}`;
    return isWebUrl(href) ? { href, label: "View on LinkedIn" } : null;
  }
  if (looksLikeUrl && isWebUrl(value)) return { href: value, label: value };
  return null;
}

// A plain http(s) address: a host (with an optional port) and then an optional path.
function isWebUrl(href: string): boolean {
  return /^https?:\/\/[^\s/?#:@]+(:\d+)?([/?#]\S*)?$/i.test(href);
}
