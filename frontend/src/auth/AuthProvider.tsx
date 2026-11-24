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
}

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
      uid.current = next;
      if (!user) {
        setState({ phase: "signed_out", me: null, message: null });
        return;
      }
      setState((s) => ({ ...s, phase: "loading" }));
      void loadMe();
    });
  }, [loadMe]);

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
    setState((s) => ({ ...s, message: null }));
    await signInWithGoogle();
  }, []);

  const signOut = useCallback(async () => {
    uid.current = null;
    await signOutOfGoogle();
    setState({ phase: "signed_out", me: null, message: null });
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      ...state,
      can: (action: string) =>
        state.phase === "granted" && (state.me?.actions ?? []).includes(action),
      signIn,
      signOut,
      refresh: loadMe,
    }),
    [state, signIn, signOut, loadMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
