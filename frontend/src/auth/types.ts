// Sign-in and the Users page (Phase 9); mirrors backend/app/modules/auth/schemas.py.

export type UserRole = "admin" | "manager" | "rep";
export type UserStatus = "active" | "disabled";

export type AppUser = {
  id: string;
  email: string;
  display_name: string | null;
  role: UserRole;
  status: UserStatus;
  last_sign_in_at: string | null;
  invited_by: string | null;
  created_at: string;
  // False until an invited person signs in for the first time.
  has_signed_in: boolean;
  // Who invited them (name or email); empty for the first admin.
  invited_by_name?: string | null;
};

// Who is signed in. "granted" comes with the user and the actions their role allows; "none" is a
// verified InfoBeans account with no invitation yet; "disabled" was switched off by an admin.
export type Me = {
  access: "granted" | "none" | "disabled";
  email: string;
  name: string | null;
  user: AppUser | null;
  actions: string[];
  request_pending: boolean;
};

export type AccessRequest = {
  id: string;
  email: string;
  display_name: string | null;
  message: string | null;
  status: "pending" | "approved" | "dismissed";
  requested_at: string;
  decided_at: string | null;
};

// The actions the permission table knows (backend/app/modules/auth/permissions.py).
export const ACTIONS = {
  usersManage: "users.manage",
  usersGrantAdmin: "users.grant_admin",
  usageView: "usage.view",
  offeringsManage: "offerings.manage",
  roleCategoriesManage: "role_categories.manage",
  documentsManage: "documents.manage",
  documentsDelete: "documents.delete",
  bulkJobs: "bulk.jobs",
  bulkDismiss: "bulk.dismiss",
} as const;

export const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Admin",
  manager: "Manager",
  rep: "Rep",
};
