import { Check } from "lucide-react";

import { useAuth } from "@/auth/AuthProvider";
import { ROLE_LABEL } from "@/auth/types";
import { PageHeader } from "@/components/PageHeader";
import { ACTION_LABEL, initials } from "@/features/users/userLabels";
import { formatDate, timeAgo } from "@/lib/format";

// The signed-in person's own account: who they are, their role, and what that role lets them do.
// Name and photo come from their Google account; the role is set by an admin on User Management.
export function ProfilePage() {
  const { me } = useAuth();
  const user = me?.user;
  if (!me || !user) return null;
  const name = me.name ?? user.display_name ?? user.email;

  const facts: [string, string][] = [
    ["Email", user.email],
    ["Role", ROLE_LABEL[user.role]],
    ["Status", user.status === "active" ? "Active" : "Deactivated"],
    [
      "Last signed in",
      user.last_sign_in_at ? timeAgo(user.last_sign_in_at) : "Just now",
    ],
    ["Member since", formatDate(user.created_at)],
    ...(user.invited_by_name
      ? ([["Added by", user.invited_by_name]] as [string, string][])
      : []),
  ];

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Profile"
        description="Your account in Sales Intelligence."
      />
      <section className="flex items-center gap-5 border border-border bg-card p-6">
        <span
          className="grid size-16 shrink-0 place-items-center rounded-full bg-sidebar text-xl font-semibold text-white"
          aria-hidden="true"
        >
          {initials(me.name ?? user.display_name, user.email)}
        </span>
        <div className="min-w-0">
          <h2 className="truncate text-xl font-bold">{name}</h2>
          <p className="truncate text-sm text-muted-foreground">{user.email}</p>
          <span className="mt-2 inline-block bg-accent px-2 py-0.5 text-xs font-semibold text-primary-text">
            {ROLE_LABEL[user.role]}
          </span>
        </div>
      </section>

      <dl className="mt-6 grid gap-x-8 gap-y-4 border border-border bg-card p-6 text-sm sm:grid-cols-2">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {label}
            </dt>
            <dd className="mt-1">{value}</dd>
          </div>
        ))}
      </dl>

      <section className="mt-6 border border-border bg-card p-6">
        <h2 className="text-lg font-bold">What your role can do</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Besides the everyday work (searches, Quick Check, companies, drafts
          and outreach), which everyone can do.
        </p>
        <ul className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          {me.actions.map((action) => (
            <li key={action} className="flex items-start gap-2">
              <Check
                className="mt-0.5 size-4 shrink-0 text-chip-success-fg"
                aria-hidden="true"
              />
              {ACTION_LABEL[action] ?? action}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted-foreground">
          Your name comes from your Google account. Your role is set by an admin
          on User Management.
        </p>
      </section>
    </div>
  );
}
