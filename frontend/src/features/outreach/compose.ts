import type { Contact } from "@/api/types";

// TEMPORARY. Part of the stopgap in SendFromMail.tsx, which goes when the app is connected to the
// rep's own Gmail and can send and sync by itself.

// Browsers and mail sites cut very long addresses, so a draft that would not fit is copied instead.
export const MAX_COMPOSE_URL = 1900;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function emailOf(contact: Pick<Contact, "channels">): string | null {
  const found = contact.channels.find(
    (c) => c.channel_type === "email" && EMAIL.test(c.value.trim()),
  );
  return found ? found.value.trim() : null;
}

export function linkedinUrlOf(
  contact: Pick<Contact, "channels">,
): string | null {
  const found = contact.channels.find(
    (c) => c.channel_type === "linkedin" && /^https?:\/\//i.test(c.value),
  );
  return found ? found.value.trim() : null;
}

// A Gmail compose link with the recipient, subject and body filled in. It opens in whichever Gmail
// account the rep is signed in to, so the message comes from them. Null when it would be too long.
export function gmailComposeUrl({
  to,
  subject,
  body,
}: {
  to: string;
  subject: string;
  body: string;
}): string | null {
  const enc = encodeURIComponent;
  const url = `https://mail.google.com/mail/?view=cm&fs=1&to=${enc(to)}&su=${enc(subject)}&body=${enc(body)}`;
  return url.length <= MAX_COMPOSE_URL ? url : null;
}

// What "Copy" puts on the clipboard.
export function composeText(subject: string, body: string): string {
  return subject.trim() ? `Subject: ${subject.trim()}\n\n${body}` : body;
}
