import { ROLE_LABEL, type AppUser, type UserRole } from "@/auth/types";
import { timeAgo } from "@/lib/format";

// The roles someone may hand out: an admin can make admins, a manager only managers and reps.
export function roleOptions(
  canGrantAdmin: boolean,
): { value: UserRole; label: string }[] {
  const roles: UserRole[] = canGrantAdmin
    ? ["rep", "manager", "admin"]
    : ["rep", "manager"];
  return roles.map((value) => ({ value, label: ROLE_LABEL[value] }));
}

// "Not yet (invited)" until the first sign-in, then when they last signed in.
export function signedInLabel(
  user: Pick<AppUser, "has_signed_in" | "last_sign_in_at">,
  now?: number,
): string {
  if (!user.has_signed_in) return "Not yet (invited)";
  return user.last_sign_in_at ? timeAgo(user.last_sign_in_at, now) : "Yes";
}

// Up to two letters for the avatar: first and last name, else the start of the email.
export function initials(
  name: string | null | undefined,
  email: string,
): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2)
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return email.slice(0, 2).toUpperCase();
}

// What each permission means, in plain words, for the profile page.
export const ACTION_LABEL: Record<string, string> = {
  "users.manage": "Manage users and access requests",
  "users.grant_admin": "Make someone an admin",
  "usage.view": "See AI and search costs",
  "offerings.manage": "Manage our offerings",
  "role_categories.manage": "Manage role categories",
  "documents.manage": "Upload and manage documents",
  "documents.delete": "Delete documents",
  "bulk.jobs": "Run bulk jobs (scrape, verify, qualify)",
  "bulk.dismiss": 'Mark many companies "not a fit" at once',
};

export type UserState = "active" | "invited" | "deactivated";

// Deactivated beats everything; an active account nobody has signed in to yet is an invitation.
export function userState(
  user: Pick<AppUser, "status" | "has_signed_in">,
): UserState {
  if (user.status === "disabled") return "deactivated";
  return user.has_signed_in ? "active" : "invited";
}

// "4 active · 1 invited · 2 waiting for access" above the list.
export function peopleSummary(
  users: Pick<AppUser, "status" | "has_signed_in">[],
  waiting: number,
): string {
  const counts = { active: 0, invited: 0, deactivated: 0 };
  for (const user of users) counts[userState(user)] += 1;
  const parts = [`${counts.active} active`];
  if (counts.invited) parts.push(`${counts.invited} invited`);
  if (counts.deactivated) parts.push(`${counts.deactivated} deactivated`);
  if (waiting) parts.push(`${waiting} waiting for access`);
  return parts.join(" · ");
}
