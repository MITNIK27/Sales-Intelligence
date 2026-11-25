import { onIdTokenChanged } from "firebase/auth";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, SIGNED_OUT_EVENT, apiGet } from "@/api/client";
import {
  firebaseAuth,
  firebaseConfigured,
  signInWithGoogle,
  signOutOfGoogle,
} from "@/auth/firebase";
import {
  IDLE_LIMIT_MS,
  IDLE_WARNING_MS,
  clearIdleSignedOut,
  idleFor,
  isIdleExpired,
  lastActive,
  markActive,
  markIdleSignedOut,
  wasIdleSignedOut,
} from "@/auth/idle";
import type { Me } from "@/auth/types";

// Where the person stands. "granted" is the only phase in which the app itself is shown.
export type AuthPhase =
  | "loading"
  | "not_configured"
  | "signed_out"
  | "refused" // Google sign-in worked but the account is not allowed (another domain...)
  | "no_access" // allowed account, no invitation yet
  | "disabled"
  | "granted"
  // Signed out after an hour without activity, with the app still on screen behind a sign-in
  // panel, so nothing typed is lost; signing in again as the same person carries on.
  | "locked"
  | "error";

interface AuthState {
  phase: AuthPhase;
  me: Me | null;
  message: string | null;
}

interface AuthValue extends AuthState {
  can: (action: string) => boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  // Time left before the idle sign-out, only while the warning is due (null otherwise).
  idleLeftMs: number | null;
  stayActive: () => void;
}

export const IDLE_MESSAGE =
  "You were signed out after 60 minutes without activity. Sign in to carry on.";

// What counts as someone using the app. Mouse movement alone does not.
const ACTIVITY_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"];
// Activity is written to storage at most this often.
const ACTIVITY_WRITE_MS = 5000;

const AuthContext = createContext<AuthValue | null>(null);

// Who is signed in, from Firebase (identity) and our API (access, role, allowed actions). Wraps the
// whole app; `useAuth()` reads it anywhere.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    phase: firebaseConfigured ? "loading" : "not_configured",
    me: null,
    message: null,
  });
  // The account last seen; undefined until Firebase has reported once.
  const uid = useRef<string | null | undefined>(undefined);
  // The account whose screen is locked, so only that person unlocks it in place.
  const lockedUid = useRef<string | null>(null);
  const phaseRef = useRef<AuthPhase>(state.phase);
  useEffect(() => {
    phaseRef.current = state.phase;
  }, [state.phase]);
  const [idleLeftMs, setIdleLeftMs] = useState<number | null>(null);

  const loadMe = useCallback(async () => {
    try {
      const me = await apiGet<Me>("/auth/me");
      const phase: AuthPhase = me.access === "none" ? "no_access" : me.access;
      setState({ phase, me, message: null });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setState({ phase: "signed_out", me: null, message: err.message });
      } else if (err instanceof ApiError && err.status === 403) {
        setState({ phase: "refused", me: null, message: err.message });
      } else {
        setState({
          phase: "error",
          me: null,
          message:
            err instanceof Error ? err.message : "Could not check your access.",
        });
      }
    }
  }, []);

  useEffect(() => {
    const auth = firebaseAuth();
    if (!auth) return;
    // Fires on sign-in, sign-out and every hourly token refresh; access is only re-read when the
    // signed-in account changes.
    return onIdTokenChanged(auth, (user) => {
      const next = user?.uid ?? null;
      if (next === uid.current) return;
      const firstReport = uid.current === undefined;
      const previous = uid.current ?? null;
      uid.current = next;

      if (!user) {
        // Signed out for being idle (here or in another tab): lock the screen and keep the page.
        if (
          wasIdleSignedOut() &&
          (phaseRef.current === "granted" || phaseRef.current === "locked")
        ) {
          lockedUid.current = lockedUid.current ?? previous;
          setState((s) => ({ ...s, phase: "locked", message: IDLE_MESSAGE }));
          return;
        }
        setState((s) => ({
          phase: "signed_out",
          me: null,
          message: s.phase === "signed_out" ? s.message : null,
        }));
        return;
      }

      // A sign-in remembered by the browser, but unused for longer than the limit (for example the
      // browser was closed for the afternoon): ask to sign in again. Nothing is on screen yet, so
      // there is nothing to keep.
      if (firstReport && isIdleExpired()) {
        uid.current = null;
        clearIdleSignedOut();
        setState({ phase: "signed_out", me: null, message: IDLE_MESSAGE });
        void signOutOfGoogle();
        return;
      }

      // Someone else unlocked a locked screen: start clean so nothing of the last person's work
      // stays on screen.
      if (lockedUid.current && lockedUid.current !== next) {
        window.location.assign("/");
        return;
      }
      lockedUid.current = null;
      if (phaseRef.current !== "locked")
        setState((s) => ({ ...s, phase: "loading" }));
      void loadMe();
    });
  }, [loadMe]);

  // While someone is using the app: note their activity and sign them out after the idle limit,
  // with a warning shortly before. Storage is shared, so activity in any tab counts.
  const granted = state.phase === "granted";
  useEffect(() => {
    if (!granted) {
      setIdleLeftMs(null);
      return;
    }
    if (lastActive() === null) markActive();
    let lastWrite = 0;
    const onActivity = () => {
      const now = Date.now();
      if (now - lastWrite < ACTIVITY_WRITE_MS) return;
      lastWrite = now;
      markActive(now);
    };
    ACTIVITY_EVENTS.forEach((name) =>
      window.addEventListener(name, onActivity, { passive: true }),
    );
    const timer = window.setInterval(() => {
      const left = IDLE_LIMIT_MS - idleFor();
      if (left <= 0) {
        markIdleSignedOut();
        lockedUid.current = uid.current ?? null;
        setState((s) => ({ ...s, phase: "locked", message: IDLE_MESSAGE }));
        void signOutOfGoogle();
        return;
      }
      setIdleLeftMs(left <= IDLE_WARNING_MS ? left : null);
    }, 1000);
    return () => {
      ACTIVITY_EVENTS.forEach((name) =>
        window.removeEventListener(name, onActivity),
      );
      window.clearInterval(timer);
    };
  }, [granted]);

  const stayActive = useCallback(() => {
    markActive();
    setIdleLeftMs(null);
  }, []);

  useEffect(() => {
    // The API said the sign-in is no longer accepted (expired, or the account was removed).
    const onSignedOut = () =>
      setState((s) =>
        s.phase === "granted"
          ? {
              phase: "signed_out",
              me: null,
              message: "Your sign-in has ended. Sign in again.",
            }
          : s,
      );
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, []);

  const signIn = useCallback(async () => {
    setState((s) => ({
      ...s,
      message: s.phase === "locked" ? s.message : null,
    }));
    await signInWithGoogle();
    // Signed in: the idle clock starts again and the other tabs stop showing the lock.
    markActive();
    clearIdleSignedOut();
  }, []);

  const signOut = useCallback(async () => {
    uid.current = null;
    lockedUid.current = null;
    clearIdleSignedOut();
    await signOutOfGoogle();
    setState({ phase: "signed_out", me: null, message: null });
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      ...state,
      can: (action: string) =>
        // While locked the page behind stays as it was, so a role-only page is not sent home.
        (state.phase === "granted" || state.phase === "locked") &&
        (state.me?.actions ?? []).includes(action),
      signIn,
      signOut,
      refresh: loadMe,
      idleLeftMs,
      stayActive,
    }),
    [state, signIn, signOut, loadMe, idleLeftMs, stayActive],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
