import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check,
  ChevronDown,
  Circle,
  Loader2,
  Search,
  SlidersHorizontal,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  quickLook,
  saveSnapshot,
  type Candidate,
  type QuickLookRequest,
  type Snapshot,
} from "@/features/quicklook/api";
import { AdvancedOptions } from "@/features/quicklook/AdvancedOptions";
import { LOOKUP_STEPS, lookupStep } from "@/features/quicklook/callStyle";
import { CandidatePicker } from "@/features/quicklook/CandidatePicker";
import {
  NO_EXTRAS,
  allCriteria,
  hasExtras,
  type Extras,
} from "@/features/quicklook/extras";
import { SnapshotCard } from "@/features/quicklook/SnapshotCard";
import { usePersistentState } from "@/lib/usePersistentState";
import { cn } from "@/lib/utils";

type View =
  | { kind: "idle" }
  | { kind: "ready"; snapshot: Snapshot; notes: string[] }
  | { kind: "choose"; candidates: Candidate[]; intro: string; notes: string[] }
  | { kind: "not_found"; notes: string[] };

function LookupProgress({ seconds }: { seconds: number }) {
  const current = lookupStep(seconds);
  return (
    <Card className="mt-6" aria-live="polite">
      <CardContent>
        <ol className="flex flex-col gap-2">
          {LOOKUP_STEPS.map((label, index) => (
            <li
              key={label}
              className={cn(
                "flex items-center gap-2 text-sm",
                index > current ? "text-muted-foreground" : "text-foreground",
              )}
            >
              {index < current ? (
                <Check
                  className="size-4 text-chip-success-fg"
                  aria-hidden="true"
                />
              ) : index === current ? (
                <Loader2
                  className="size-4 animate-spin text-primary"
                  aria-hidden="true"
                />
              ) : (
                <Circle className="size-4" aria-hidden="true" />
              )}
              {label}
            </li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-muted-foreground">
          This usually takes 10 to 20 seconds.
        </p>
      </CardContent>
    </Card>
  );
}

// Quick Check: type a company name and get a short answer, with a clear call on whether it is
// worth pitching. Going deeper is one click away; optional extras (an area to research and the
// person's own criteria) sit under Advanced and never block the look-up.
export function QuickLookPage() {
  const navigate = useNavigate();
  const [company, setCompany] = usePersistentState("quickcheck.company", "");
  const [extras, setExtras] = useState<Extras>(NO_EXTRAS);
  const [view, setView] = useState<View>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [looking, setLooking] = useState(false);
  // A short message for work that happens with the current answer still on screen ("not this one",
  // refresh). The answer stays visible, dimmed, instead of being replaced by the look-up steps.
  const [quietNote, setQuietNote] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [working, setWorking] = useState<"save" | "deeper" | "refresh" | null>(
    null,
  );
  const [savedCompanyId, setSavedCompanyId] = useState<string | null>(null);
  // Websites the person rejected for this search, so they are not offered again.
  const avoid = useRef<string[]>([]);
  const asked = useRef("");

  useEffect(() => {
    if (!looking) return;
    setSeconds(0);
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [looking]);

  async function run(
    request: QuickLookRequest,
    intro?: string,
    quiet?: string,
  ) {
    setError(null);
    setQuietNote(quiet ?? null);
    setLooking(true);
    setSavedCompanyId(null);
    try {
      const answer = await quickLook({
        ...request,
        avoid: avoid.current,
        focus: extras.focus.trim() || undefined,
        criteria: allCriteria(extras),
      });
      if (answer.status === "ready" && answer.snapshot) {
        setView({
          kind: "ready",
          snapshot: answer.snapshot,
          notes: answer.notes,
        });
      } else if (answer.status === "needs_choice") {
        setView({
          kind: "choose",
          candidates: answer.candidates,
          intro:
            intro ??
            "More than one company matches that name. Pick the right one.",
          notes: answer.notes,
        });
      } else {
        setView({ kind: "not_found", notes: answer.notes });
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "The look-up did not work. Try again.",
      );
    } finally {
      setLooking(false);
      setQuietNote(null);
      setWorking(null);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = company.trim();
    if (!text || looking) return;
    avoid.current = [];
    asked.current = text;
    void run({ company: text });
  }

  function choose(domain: string, name: string) {
    void run({ company: name, domain });
  }

  function refine(text: string) {
    asked.current = text;
    void run({ company: text });
  }

  function notThisOne(snapshot: Snapshot) {
    avoid.current = [...avoid.current, snapshot.domain];
    void run(
      { company: asked.current || snapshot.name, always_ask: true },
      "Here are the other matches. If none is right, paste the website below.",
      "Finding other matches…",
    );
  }

  async function save(snapshot: Snapshot, goDeeper: boolean) {
    setWorking(goDeeper ? "deeper" : "save");
    setError(null);
    try {
      const saved = await saveSnapshot(snapshot.id, goDeeper);
      if (goDeeper) navigate(`/companies/${saved.company_id}`);
      else setSavedCompanyId(saved.company_id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "That could not be saved. Try again.",
      );
    } finally {
      setWorking(null);
    }
  }

  function refresh(snapshot: Snapshot) {
    setWorking("refresh");
    void run(
      { company: snapshot.name, domain: snapshot.domain, refresh: true },
      undefined,
      "Refreshing the answer…",
    );
  }

  return (
    <div>
      <PageHeader
        title="Quick Check"
        description="Type a company name. You get a short answer on what they do and whether they are worth pitching."
      />

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-2">
            <Label htmlFor="lookup-company" className="sr-only">
              Company name or website
            </Label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <Search
                  className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  id="lookup-company"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Company name, for example Infor"
                  maxLength={200}
                  autoFocus
                  className="h-12 pl-10 text-base"
                />
              </div>
              <Button
                type="submit"
                disabled={!company.trim() || looking}
                className="h-12 px-6"
              >
                {looking ? "Looking…" : "Look up"}
              </Button>
            </div>
          </form>
          {error && (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {error}
            </p>
          )}
        </CardContent>
      </Card>

      <details className="group mt-4 rounded-xl border border-foreground/25 bg-background shadow-sm">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 font-semibold focus-visible:ring-3 focus-visible:ring-ring/50">
          <span className="flex items-center gap-2">
            <SlidersHorizontal className="size-4" aria-hidden="true" />
            Advanced
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              research an area, check your own criteria
              {hasExtras(extras) ? " (in use)" : ""}
            </span>
          </span>
          <ChevronDown
            className="size-5 transition group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
        <div className="border-t border-border px-5 py-5">
          <AdvancedOptions extras={extras} onChange={setExtras} />
        </div>
      </details>

      {looking && !quietNote && <LookupProgress seconds={seconds} />}

      {view.kind === "ready" && (!looking || quietNote) && (
        <div
          className={cn(
            "transition-opacity duration-200",
            quietNote && "pointer-events-none opacity-50",
          )}
          aria-busy={quietNote ? true : undefined}
        >
          {quietNote && (
            <p
              role="status"
              className="mt-6 flex items-center gap-2 text-sm font-medium"
            >
              <Loader2
                className="size-4 animate-spin text-primary"
                aria-hidden="true"
              />
              {quietNote}
            </p>
          )}
          <SnapshotCard
            snapshot={view.snapshot}
            notes={view.notes}
            actions={{
              working,
              savedCompanyId,
              onGoDeeper: () => void save(view.snapshot, true),
              onSave: () => void save(view.snapshot, false),
              onRefresh: () => refresh(view.snapshot),
              onNotThisOne: () => notThisOne(view.snapshot),
            }}
          />
        </div>
      )}

      {!looking && view.kind === "choose" && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
          <CandidatePicker
            candidates={view.candidates}
            intro={view.intro}
            disabled={looking}
            onChoose={choose}
            onRefine={refine}
          />
          {view.notes.length > 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              {view.notes.join(" ")}
            </p>
          )}
        </div>
      )}

      {!looking && view.kind === "not_found" && (
        <>
          <Card className="mt-6">
            <CardContent>
              <h2 className="text-lg font-bold">No company found</h2>
              <p className="text-sm text-muted-foreground">
                {view.notes.join(" ") ||
                  "Nothing matched that name. Check the spelling, or paste the company's website."}
              </p>
            </CardContent>
          </Card>
          <CandidatePicker
            candidates={[]}
            intro="Try the full name or paste the website."
            disabled={looking}
            onChoose={choose}
            onRefine={refine}
          />
        </>
      )}
    </div>
  );
}
