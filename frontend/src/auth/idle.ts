// Signing out after a period without activity. The time of the last activity is kept in the
// browser's storage, so every open tab shares it (working in one tab keeps the others signed in)
// and it still counts after the browser was closed: coming back after more than the limit means
// signing in again.

export const IDLE_LIMIT_MS = 60 * 60 * 1000;
// How long before the limit the "Still there?" notice appears.
export const IDLE_WARNING_MS = 2 * 60 * 1000;

const LAST_ACTIVE_KEY = "si.auth.lastActive";
// Set when the app signed the person out for being idle (not when they pressed Sign out), so every
// tab locks its screen instead of leaving the page.
const IDLE_SIGNED_OUT_KEY = "si.auth.idleSignedOut";

function read(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(key);
    const value = raw === null ? NaN : Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function write(key: string, value: number | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, String(value));
  } catch {
    // Storage blocked: idle sign-out then only works within this tab's lifetime.
  }
}

export function markActive(now: number = Date.now()): void {
  write(LAST_ACTIVE_KEY, now);
}

export function lastActive(): number | null {
  return read(LAST_ACTIVE_KEY);
}

// How long since the last activity; unknown counts as too long, so a sign-in remembered from
// before this rule existed asks once.
export function idleFor(now: number = Date.now()): number {
  const last = lastActive();
  return last === null ? Number.POSITIVE_INFINITY : Math.max(0, now - last);
}

export function isIdleExpired(now: number = Date.now()): boolean {
  return idleFor(now) >= IDLE_LIMIT_MS;
}

export function markIdleSignedOut(now: number = Date.now()): void {
  write(IDLE_SIGNED_OUT_KEY, now);
}

export function wasIdleSignedOut(): boolean {
  return read(IDLE_SIGNED_OUT_KEY) !== null;
}

export function clearIdleSignedOut(): void {
  write(IDLE_SIGNED_OUT_KEY, null);
}

// "2:00", "0:45".
export function countdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
