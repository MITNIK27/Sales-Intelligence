import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check,
  ChevronDown,
  Circle,
  History,
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
  checkAnswer,
  quickLook,
  saveSnapshot,
  type Candidate,
  type QuickLookRequest,
  type Snapshot,
} from "@/features/quicklook/api";
import { QuickCheckHistory } from "@/features/quicklook/QuickCheckHistory";
import { formatDateTime } from "@/lib/format";
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

// An answer from the person's history, shown as it was given then.
type Earlier = { entryId: string; checkedAt: string; criteria: string[] };

type View =
  | { kind: "idle" }
  | { kind: "ready"; snapshot: Snapshot; notes: string[]; earlier?: Earlier }
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
  // Bumped after each answer, so the history list below picks up the new check.
  const [historyVersion, setHistoryVersion] = useState(0);
  const [openingEarlier, setOpeningEarlier] = useState(false);

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
    // The extras to use instead of what is in Advanced (checking an earlier answer again).
    using: Extras = extras,
  ) {
    setError(null);
    setQuietNote(quiet ?? null);
    setLooking(true);
    setSavedCompanyId(null);
    try {
      const answer = await quickLook({
        ...request,
        avoid: avoid.current,
        focus: using.focus.trim() || undefined,
        criteria: allCriteria(using),
      });
      if (answer.status === "ready" && answer.snapshot) {
        setView({
          kind: "ready",
          snapshot: answer.snapshot,
          notes: answer.notes,
        });
        setHistoryVersion((v) => v + 1);
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

  // The extras an earlier answer was given for, so checking it again asks the same questions.
  function extrasOf(snapshot: Snapshot, earlier: Earlier): Extras {
    return { focus: snapshot.focus ?? "", custom: earlier.criteria };
  }

  function refresh(snapshot: Snapshot, earlier?: Earlier) {
    setWorking("refresh");
    const using = earlier ? extrasOf(snapshot, earlier) : extras;
    if (earlier) setExtras(using);
    void run(
      { company: snapshot.name, domain: snapshot.domain, refresh: true },
      undefined,
      "Refreshing the answer…",
      using,
    );
  }

  // Back to the latest answer for an earlier check (free when it is still fresh).
  function latest(snapshot: Snapshot, earlier: Earlier) {
    const using = extrasOf(snapshot, earlier);
    setExtras(using);
    asked.current = snapshot.name;
    avoid.current = [];
    void run(
      { company: snapshot.name, domain: snapshot.domain },
      undefined,
      "Getting the latest answer…",
      using,
    );
  }

  async function openEarlier(entryId: string) {
    setError(null);
    setOpeningEarlier(true);
    try {
      const found = await checkAnswer(entryId);
      setSavedCompanyId(null);
      setCompany(found.answer.name);
      asked.current = found.answer.name;
      avoid.current = [];
      setView({
        kind: "ready",
        snapshot: found.answer,
        notes: [],
        earlier: {
          entryId: found.entry_id,
          checkedAt: found.checked_at,
          criteria: found.criteria,
        },
      });
      document
        .getElementById("quick-check-top")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "That check could not be opened.",
      );
    } finally {
      setOpeningEarlier(false);
    }
  }

  const earlier = view.kind === "ready" ? view.earlier : undefined;

  return (
    <div id="quick-check-top" className="scroll-mt-6">
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
          {earlier && !quietNote && (
            <div
              role="status"
              className="mt-6 flex flex-wrap items-center gap-3 border border-border border-l-4 border-l-primary bg-secondary/70 px-4 py-3 text-sm"
            >
              <History
                className="size-4 shrink-0 text-primary"
                aria-hidden="true"
              />
              <p className="min-w-0 flex-1">
                This is the answer you got on{" "}
                <span className="font-semibold">
                  {formatDateTime(earlier.checkedAt)}
                </span>
                . Things may have changed since.
              </p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => latest(view.snapshot, earlier)}
                disabled={looking}
              >
                See the latest answer
              </Button>
            </div>
          )}
          <SnapshotCard
            snapshot={view.snapshot}
            notes={view.notes}
            actions={{
              working,
              savedCompanyId,
              onGoDeeper: () => void save(view.snapshot, true),
              onSave: () => void save(view.snapshot, false),
              onRefresh: () => refresh(view.snapshot, earlier),
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

      <div
        className={cn(
          "transition-opacity duration-150",
          openingEarlier && "pointer-events-none opacity-60",
        )}
        aria-busy={openingEarlier || undefined}
      >
        <QuickCheckHistory
          version={historyVersion}
          openEntryId={earlier?.entryId ?? null}
          onOpen={(entryId) => void openEarlier(entryId)}
        />
      </div>
    </div>
  );
}
