import { initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  getAuth,
  signInWithPopup,
  signOut,
  type Auth,
} from "firebase/auth";

// Sign-in is Firebase Authentication with InfoBeans Google accounts (Phase 9). Firebase only proves
// who the person is; whether they may use the app, and with which role, is decided by our API.
// The settings come from frontend/.env.local; without them the app says sign-in is not set up.

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

// The Google Workspace domain offered first in Google's account picker. The server enforces the
// real rule (AUTH_ALLOWED_DOMAINS); this only saves picking the right account.
const HOSTED_DOMAIN = "infobeans.com";

export const firebaseConfigured = Boolean(
  config.apiKey && config.authDomain && config.projectId,
);

let auth: Auth | null = null;

export function firebaseAuth(): Auth | null {
  if (!firebaseConfigured) return null;
  if (!auth) auth = getAuth(initializeApp(config));
  return auth;
}

export async function signInWithGoogle(): Promise<void> {
  const current = firebaseAuth();
  if (!current) throw new Error("Sign-in is not set up for this app yet.");
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({
    hd: HOSTED_DOMAIN,
    prompt: "select_account",
  });
  await signInWithPopup(current, provider);
}

export async function signOutOfGoogle(): Promise<void> {
  const current = firebaseAuth();
  if (current) await signOut(current);
}

// The signed-in person's ID token for the API. Firebase keeps it fresh (it lasts an hour);
// `forceRefresh` asks for a new one after the API said the old one was not accepted.
export async function idToken(forceRefresh = false): Promise<string | null> {
  const user = firebaseAuth()?.currentUser;
  return user ? user.getIdToken(forceRefresh) : null;
}
