import { useEffect, useState } from "react";

// useState that survives leaving the page (and a browser refresh). Pages here keep their results
// in component state, so navigating to another page unmounted them and threw the results away.
// Only small identifiers/inputs are stored (a job id, the typed prompt) — big results are
// re-fetched from the server by id, so what's shown is always current, never a stale copy.
export function usePersistentState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial; // storage blocked or corrupt: behave like plain useState
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage full or blocked: the page still works, it just won't be remembered.
    }
  }, [key, value]);

  return [value, setValue] as const;
}
