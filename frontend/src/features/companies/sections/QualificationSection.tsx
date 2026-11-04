import { ClipboardCheck, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { CompanyCriterion, QualificationResult } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SkeletonLines } from "@/components/Skeleton";
import { StatusTag } from "@/components/StatusTag";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MAX_CRITERIA, MAX_CRITERION_CHARS } from "@/features/quicklook/extras";
import { QualificationResultsTable } from "@/features/qualification/QualificationResultsTable";

// The criteria kept for this company: what the person wants to know about it, typed here or on the
// Market Discovery search that found it. Checking them gives an answer for each (met, not met,
// could not determine). It never labels the company qualified or not, and nothing else on the page
// depends on it.
export function QualificationSection({
  criteria,
  results,
  error,
  onSaveCriteria,
  onCheck,
  onRetry,
}: {
  criteria: CompanyCriterion[];
  results: QualificationResult[] | null;
  error: string | null;
  onSaveCriteria: (next: CompanyCriterion[]) => Promise<void>;
  onCheck: () => Promise<void>;
  onRetry: () => void;
}) {
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [typed, setTyped] = useState("");

  async function save(next: CompanyCriterion[]) {
    setSaving(true);
    await onSaveCriteria(next);
    setSaving(false);
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    const name = typed
      .trim()
      .replace(/\s+/g, " ")
      .slice(0, MAX_CRITERION_CHARS);
    if (
      !name ||
      criteria.some((c) => c.name.toLowerCase() === name.toLowerCase())
    )
      return;
    setTyped("");
    await save([...criteria, { name, description: null, must_have: false }]);
  }

  async function check() {
    setChecking(true);
    await onCheck();
    setChecking(false);
  }

  return (
    <>
      <h2 className="mb-3 mt-8 text-lg font-bold">Criteria for this company</h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Optional. Add what you want to know about this company and check it. It
        does not label the company qualified or not.
      </p>
      <Card>
        <CardContent className="flex flex-col gap-4">
          {criteria.length > 0 && (
            <ul className="flex flex-col gap-2">
              {criteria.map((c) => (
                <li
                  key={c.name}
                  className="flex items-center justify-between gap-3 border border-border bg-card px-3 py-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="font-medium">{c.name}</span>
                    {c.description && (
                      <span className="block text-xs text-muted-foreground">
                        {c.description}
                      </span>
                    )}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {c.must_have && (
                      <StatusTag tone="neutral">
                        Must have in the search
                      </StatusTag>
                    )}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${c.name}`}
                      disabled={saving}
                      onClick={() =>
                        save(criteria.filter((x) => x.name !== c.name))
                      }
                    >
                      <X className="size-4" aria-hidden />
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={add} className="flex gap-2 sm:max-w-xl">
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder="e.g. Is expanding into new markets"
              maxLength={MAX_CRITERION_CHARS}
              aria-label="Add a criterion"
            />
            <Button
              type="submit"
              variant="action"
              disabled={
                !typed.trim() || saving || criteria.length >= MAX_CRITERIA
              }
            >
              Add
            </Button>
          </form>

          <div>
            <Button
              type="button"
              onClick={check}
              disabled={checking || criteria.length === 0}
            >
              {checking ? "Checking…" : "Check this company"}
            </Button>
            {criteria.length === 0 && (
              <p className="mt-2 text-sm text-muted-foreground">
                Add at least one criterion to check.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="mt-4">
        {error ? (
          <Card>
            <ErrorState message={error} onRetry={onRetry} />
          </Card>
        ) : !results ? (
          <Card className="p-6">
            <SkeletonLines lines={4} />
          </Card>
        ) : results.length === 0 ? (
          <Card>
            <EmptyState
              icon={ClipboardCheck}
              title="No checks yet"
              description="Add criteria above and choose Check this company."
            />
          </Card>
        ) : (
          <QualificationResultsTable results={results} />
        )}
      </div>
    </>
  );
}
