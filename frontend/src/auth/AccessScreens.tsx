import {
  CheckCircle2,
  Compass,
  Loader2,
  Lock,
  Send,
  ShieldOff,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { apiPost } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AppLayout } from "@/layout/AppLayout";
import { APP_NAME } from "@/lib/app-meta";

// What happens before someone may use the app: sign in, wait for access, or find their access
// switched off. Someone signed in without access sees the normal app frame (with only the
// Dashboard in the menu) around a single card that tells them what to do next.

// --- sign in ------------------------------------------------------------------------------------

const HIGHLIGHTS: { icon: LucideIcon; text: string }[] = [
  { icon: Compass, text: "Find companies that fit what we sell" },
  { icon: Zap, text: "Check any company in seconds" },
  { icon: Send, text: "Write outreach backed by evidence" },
];

export function SignInPage() {
  const { phase, message, signIn, signOut } = useAuth();
  const location = useLocation();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (phase === "granted" || phase === "no_access" || phase === "disabled")
    return <Navigate to={from} replace />;

  const start = async () => {
    setError(null);
    setWorking(true);
    try {
      await signIn();
    } catch (err) {
      const code = (err as { code?: string }).code ?? "";
      if (
        code !== "auth/popup-closed-by-user" &&
        code !== "auth/cancelled-popup-request"
      )
        setError(
          code === "auth/popup-blocked"
            ? "Your browser blocked the Google window. Allow pop-ups for this site and try again."
            : "Sign-in did not finish. Try again.",
        );
    } finally {
      setWorking(false);
    }
  };

  const problem =
    error ?? (phase === "refused" || phase === "error" ? message : null);

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-[1.1fr_1fr]">
      {/* Brand side: the dark of the sidebar, plain. */}
      <section className="relative hidden overflow-hidden bg-sidebar p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <Logo on="dark" className="relative h-11" />
        <div className="relative max-w-md">
          <h2 className="text-4xl font-bold leading-tight">
            Find the right companies.
            <br />
            <span className="text-white/60">Say the right thing.</span>
          </h2>
          <ul className="mt-8 flex flex-col gap-4">
            {HIGHLIGHTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-white/85">
                <span className="grid size-9 place-items-center rounded-md border border-white/15 text-primary">
                  <Icon className="size-4" aria-hidden="true" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-white/40">
          {APP_NAME} · for InfoBeans teams
        </p>
      </section>

      {/* Sign-in side */}
      <section className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          <Logo className="mb-10 h-10 lg:hidden" />
          <h1 className="text-3xl font-bold">Welcome</h1>
          <p className="mt-2 text-muted-foreground">
            Sign in to {APP_NAME} with your InfoBeans Google account.
          </p>

          {phase === "not_configured" ? (
            <p className="mt-8 border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-sm text-destructive">
              Sign-in is not set up for this copy of the app: the Firebase
              settings in frontend/.env.local are missing.
            </p>
          ) : (
            <button
              type="button"
              onClick={() => void start()}
              disabled={working || phase === "loading"}
              className="mt-8 flex h-11 w-full items-center justify-center gap-3 rounded-md border border-border bg-card text-sm font-semibold text-foreground transition-colors duration-150 hover:border-foreground/30 hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-wait disabled:opacity-70 motion-reduce:transition-none"
            >
              {working || phase === "loading" ? (
                <Loader2
                  className="size-5 animate-spin text-muted-foreground motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : (
                <GoogleMark />
              )}
              {working ? "Waiting for Google…" : "Continue with Google"}
            </button>
          )}

          {problem && (
            <div
              className="mt-4 border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-sm text-destructive"
              role="alert"
            >
              {problem}
              {phase === "refused" && (
                <button
                  type="button"
                  onClick={() => void signOut()}
                  className="mt-1 block font-semibold underline-offset-2 hover:underline"
                >
                  Use another account
                </button>
              )}
            </div>
          )}

          <p className="mt-8 flex items-start gap-2 text-xs text-muted-foreground">
            <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            Access is by invitation. New here? Sign in, then ask an admin for
            access.
          </p>
        </div>
      </section>
    </main>
  );
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-5" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"
      />
    </svg>
  );
}

// --- signed in, but not let in -------------------------------------------------------------------

function EmptyStateCard({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto mt-10 max-w-lg border border-border bg-card p-8 text-center shadow-sm">
      <span className="mx-auto grid size-14 place-items-center rounded-full bg-accent text-primary-text">
        <Icon className="size-7" aria-hidden="true" />
      </span>
      <h1 className="mt-4 text-2xl font-bold">{title}</h1>
      <div className="mt-3 flex flex-col gap-4 text-sm">{children}</div>
    </div>
  );
}

function RequestAccess() {
  const { me, refresh } = useAuth();
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<string | null>(
    me?.request_pending
      ? "Your request is waiting for an admin. You will get in as soon as they approve it."
      : null,
  );
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    setSending(true);
    setError(null);
    try {
      const result = await apiPost<{ already_waiting: boolean }>(
        "/auth/access-requests",
        { message: note.trim() || null },
      );
      setSent(
        result.already_waiting
          ? "You already asked in the last 24 hours. Your request is waiting for an admin."
          : "Request sent. An admin will see it and let you in.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work.");
    } finally {
      setSending(false);
    }
  };

  return (
    <EmptyStateCard icon={Lock} title="You need access to continue">
      <p className="text-muted-foreground">
        You are signed in as{" "}
        <span className="font-semibold text-foreground">{me?.email}</span>, but
        nobody has given this account access yet.
      </p>
      {sent ? (
        <p className="flex items-start gap-2 bg-chip-success-bg px-3 py-2 text-left text-chip-success-fg">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {sent}
        </p>
      ) : (
        <>
          <Textarea
            aria-label="Note for the admin (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={1000}
            rows={3}
            placeholder="Optional: your team and why you need access"
          />
          <Button
            type="button"
            onClick={() => void ask()}
            disabled={sending}
            className="w-full"
          >
            {sending && (
              <Loader2
                className="size-4 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            )}
            Request access
          </Button>
        </>
      )}
      {error && (
        <p className="text-destructive" role="alert">
          {error}
        </p>
      )}
      <Button
        type="button"
        variant="ghost"
        onClick={() => void refresh()}
        className="mx-auto"
      >
        I've been given access — check again
      </Button>
    </EmptyStateCard>
  );
}

function Deactivated() {
  const { me } = useAuth();
  return (
    <EmptyStateCard icon={ShieldOff} title="Your access is switched off">
      <p className="text-muted-foreground">
        An admin has deactivated{" "}
        <span className="font-semibold text-foreground">{me?.email}</span>. If
        you think this is a mistake, ask an admin to reactivate you.
      </p>
    </EmptyStateCard>
  );
}

function Waiting() {
  return (
    <main
      className="grid min-h-screen place-items-center bg-background"
      aria-busy="true"
    >
      <Loader2
        className="size-6 animate-spin text-muted-foreground motion-reduce:animate-none"
        aria-label="Checking your sign-in"
      />
    </main>
  );
}

// In front of the whole app: the app itself for people with access; the app frame with one card
// for people signed in without it; the sign-in page for everyone else.
export function RequireAccess() {
  const { phase } = useAuth();
  const location = useLocation();
  if (phase === "loading") return <Waiting />;
  if (phase === "no_access")
    return (
      <AppLayout limited>
        <RequestAccess />
      </AppLayout>
    );
  if (phase === "disabled")
    return (
      <AppLayout limited>
        <Deactivated />
      </AppLayout>
    );
  if (phase !== "granted")
    return (
      <Navigate
        to="/sign-in"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  return <Outlet />;
}

// Around a page only some roles may use: anyone else is sent home instead of seeing refusals.
export function RequireAction({
  action,
  children,
}: {
  action: string;
  children: ReactNode;
}) {
  const { can } = useAuth();
  return can(action) ? <>{children}</> : <Navigate to="/" replace />;
}
