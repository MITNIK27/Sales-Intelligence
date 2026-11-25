import { Info, Loader2, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import {
  ACTIONS,
  ROLE_LABEL,
  type AccessRequest,
  type AppUser,
  type UserRole,
} from "@/auth/types";
import { PageHeader } from "@/components/PageHeader";
import { SimpleSelect } from "@/components/SimpleSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import {
  initials,
  peopleSummary,
  roleOptions,
  signedInLabel,
  userState,
  type UserState,
} from "@/features/users/userLabels";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATE_STYLE: Record<UserState, string> = {
  active: "bg-chip-success-bg text-chip-success-fg",
  invited: "bg-chip-info-bg text-chip-info-fg",
  deactivated: "bg-muted text-muted-foreground",
};
const STATE_LABEL: Record<UserState, string> = {
  active: "Active",
  invited: "Invited",
  deactivated: "Deactivated",
};

// Who may use the app (Phase 9). Access is by invitation: give someone access by email and role,
// or approve a request from someone who signed in without it. Nobody is emailed by the app. People
// who leave are deactivated, never deleted, so what they did stays attributed to them; an
// invitation nobody used can be removed. Admins and managers use this page; only admins can make
// or change admins, and nobody changes their own role.
export function UsersPage() {
  const { can, me } = useAuth();
  const { showToast } = useToast();
  const [users, setUsers] = useState<AppUser[] | null>(null);
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const grantAdmin = can(ACTIONS.usersGrantAdmin);
  const roles = roleOptions(grantAdmin);

  const load = useCallback(async () => {
    try {
      const [people, waiting] = await Promise.all([
        apiGet<AppUser[]>("/users"),
        apiGet<AccessRequest[]>("/users/access-requests"),
      ]);
      setUsers(people);
      setRequests(waiting);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load people.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (
    key: string,
    run: () => Promise<unknown>,
    done: string,
  ): Promise<boolean> => {
    setBusy(key);
    try {
      await run();
      showToast({ description: done, variant: "success" });
      await load();
      return true;
    } catch (err) {
      showToast({
        description: err instanceof Error ? err.message : "That did not work.",
      });
      return false;
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="User Management"
        description="Who can use Sales Intelligence and what they can do."
      />
      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
      {users && (
        <p className="-mt-3 mb-6 text-sm text-muted-foreground">
          {peopleSummary(users, requests.length)}
        </p>
      )}

      {requests.length > 0 && (
        <section className="mb-8" aria-label="Access requests">
          <h2 className="mb-2 text-lg font-bold">
            Waiting for access ({requests.length})
          </h2>
          <ul className="flex flex-col gap-2">
            {requests.map((request) => (
              <RequestRow
                key={request.id}
                request={request}
                roles={roles}
                busy={busy === request.id}
                onApprove={(role) =>
                  void act(
                    request.id,
                    () =>
                      apiPost(`/users/access-requests/${request.id}/approve`, {
                        role,
                      }),
                    `${request.email} can now sign in as ${ROLE_LABEL[role].toLowerCase()}.`,
                  )
                }
                onDismiss={() =>
                  void act(
                    request.id,
                    () =>
                      apiPost(`/users/access-requests/${request.id}/dismiss`),
                    `Request from ${request.email} dismissed.`,
                  )
                }
              />
            ))}
          </ul>
        </section>
      )}

      <GiveAccessForm
        roles={roles}
        busy={busy === "invite"}
        onGive={(email, role) =>
          act(
            "invite",
            () => apiPost("/users", { email, role }),
            `${email} can now sign in. Let them know.`,
          )
        }
      />

      <section className="mt-8" aria-label="People">
        <h2 className="mb-2 text-lg font-bold">People</h2>
        {!users ? (
          <Loader2
            className="size-5 animate-spin text-muted-foreground motion-reduce:animate-none"
            aria-label="Loading"
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Person</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last signed in</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <PersonRow
                  key={user.id}
                  user={user}
                  self={user.id === me?.user?.id}
                  locked={user.role === "admin" && !grantAdmin}
                  roles={roles}
                  busy={busy === user.id}
                  onRole={(role) =>
                    void act(
                      user.id,
                      () => apiPatch(`/users/${user.id}`, { role }),
                      `${user.email} is now ${ROLE_LABEL[role].toLowerCase()}.`,
                    )
                  }
                  onStatus={(status) =>
                    void act(
                      user.id,
                      () => apiPatch(`/users/${user.id}`, { status }),
                      status === "disabled"
                        ? `${user.email} is deactivated and can no longer sign in.`
                        : `${user.email} is active again.`,
                    )
                  }
                  onRemove={() => {
                    if (
                      window.confirm(
                        `Remove the invitation for ${user.email}? They will not be able to sign in.`,
                      )
                    )
                      void act(
                        user.id,
                        () => apiDelete(`/users/${user.id}`),
                        `Invitation for ${user.email} removed.`,
                      );
                  }}
                />
              ))}
            </TableBody>
          </Table>
        )}
        {!grantAdmin && (
          <p className="mt-3 text-xs text-muted-foreground">
            Only an admin can change an admin.
          </p>
        )}
      </section>
    </div>
  );
}

function Avatar({ name, email }: { name: string | null; email: string }) {
  return (
    <span
      className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-primary-text"
      aria-hidden="true"
    >
      {initials(name, email)}
    </span>
  );
}

function PersonRow({
  user,
  self,
  locked,
  roles,
  busy,
  onRole,
  onStatus,
  onRemove,
}: {
  user: AppUser;
  self: boolean;
  locked: boolean;
  roles: { value: string; label: string }[];
  busy: boolean;
  onRole: (role: UserRole) => void;
  onStatus: (status: "active" | "disabled") => void;
  onRemove: () => void;
}) {
  const state = userState(user);
  const fixed = self || locked;
  return (
    <TableRow className={cn(state === "deactivated" && "opacity-70")}>
      <TableCell className="whitespace-normal">
        <div className="flex items-center gap-3">
          <Avatar name={user.display_name} email={user.email} />
          <div className="min-w-0">
            <div className="font-semibold">
              {user.display_name ?? user.email}
              {self && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  (you)
                </span>
              )}
            </div>
            <div className="text-xs text-muted-foreground">
              {user.display_name && user.email}
              {user.display_name && user.invited_by_name && " · "}
              {user.invited_by_name && `added by ${user.invited_by_name}`}
            </div>
          </div>
        </div>
      </TableCell>
      <TableCell>
        {fixed ? (
          <span
            className="text-sm"
            title={
              self
                ? "You cannot change your own role; ask another admin."
                : "Only an admin can change an admin."
            }
          >
            {ROLE_LABEL[user.role]}
          </span>
        ) : (
          <SimpleSelect
            label={`Role of ${user.email}`}
            value={user.role}
            options={roles}
            onChange={(role) => onRole(role as UserRole)}
            className="w-32"
          />
        )}
      </TableCell>
      <TableCell>
        <span
          className={cn(
            "px-2 py-0.5 text-xs font-semibold",
            STATE_STYLE[state],
          )}
        >
          {STATE_LABEL[state]}
        </span>
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {signedInLabel(user)}
      </TableCell>
      <TableCell className="text-right">
        {!fixed && state === "invited" && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={onRemove}
          >
            Remove invitation
          </Button>
        )}
        {!fixed && state === "active" && (
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={busy}
            onClick={() => onStatus("disabled")}
          >
            Deactivate
          </Button>
        )}
        {!fixed && state === "deactivated" && (
          <Button
            type="button"
            size="sm"
            variant="action"
            disabled={busy}
            onClick={() => onStatus("active")}
          >
            Reactivate
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

function RequestRow({
  request,
  roles,
  busy,
  onApprove,
  onDismiss,
}: {
  request: AccessRequest;
  roles: { value: string; label: string }[];
  busy: boolean;
  onApprove: (role: UserRole) => void;
  onDismiss: () => void;
}) {
  const [role, setRole] = useState<UserRole>("rep");
  return (
    <li className="flex flex-wrap items-center gap-3 border border-border bg-card p-3 text-sm">
      <Avatar name={request.display_name} email={request.email} />
      <div className="min-w-0 flex-1">
        <div className="font-semibold">
          {request.display_name ?? request.email}
        </div>
        <div className="text-xs text-muted-foreground">
          {request.email} · asked {timeAgo(request.requested_at)}
        </div>
        {request.message && <p className="mt-1">“{request.message}”</p>}
      </div>
      <SimpleSelect
        label={`Role for ${request.email}`}
        value={role}
        options={roles}
        onChange={(value) => setRole(value as UserRole)}
        className="w-32"
      />
      <Button
        type="button"
        size="sm"
        disabled={busy}
        onClick={() => onApprove(role)}
      >
        Approve
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={onDismiss}
      >
        Dismiss
      </Button>
    </li>
  );
}

function GiveAccessForm({
  roles,
  busy,
  onGive,
}: {
  roles: { value: string; label: string }[];
  busy: boolean;
  onGive: (email: string, role: UserRole) => Promise<boolean>;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("rep");
  return (
    <form
      className="border border-border bg-card p-4"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        const address = email.trim();
        if (address)
          void onGive(address, role).then((ok) => ok && setEmail(""));
      }}
    >
      <h2 className="flex items-center gap-2 text-lg font-bold">
        <UserPlus className="size-5 text-primary-text" aria-hidden="true" />
        Give someone access
      </h2>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
          <span className="font-semibold">InfoBeans email</span>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@infobeans.com"
            required
          />
        </label>
        <SimpleSelect
          label="Role"
          value={role}
          options={roles}
          onChange={(value) => setRole(value as UserRole)}
          className="w-32"
          tall
        />
        <Button type="submit" disabled={busy || !email.trim()}>
          Give access
        </Button>
      </div>
      <p className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        They can sign in with Google straight away. No email is sent, so let
        them know.
      </p>
    </form>
  );
}
