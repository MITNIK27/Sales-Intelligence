import { ListChecks } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiGet, apiPatch, apiPost } from "@/api/client";
import { CHANNEL_LABELS } from "@/api/types";
import type { ContactTrackingUpdate, FollowUpItem } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { SimpleSelect } from "@/components/SimpleSelect";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ErrorState";
import { SkeletonLines } from "@/components/Skeleton";
import { TablePagination } from "@/components/TablePagination";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { dueLabel, sequenceStatus } from "@/features/outreach/outreachRules";
import { formatDate } from "@/lib/format";

const SNOOZES = [
  { value: "1", label: "Remind me in 1 day" },
  { value: "2", label: "Remind me in 2 days" },
  { value: "5", label: "Remind me in 1 week" },
];

// Opens the person on the company's People tab, on the draft tab, which starts on the next email.
const writeLink = (item: FollowUpItem) =>
  `/companies/${item.company.id}?tab=people&contact=${item.id}&open=draft`;

export function FollowUpsPage() {
  const [items, setItems] = useState<FollowUpItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [busy, setBusy] = useState<string | null>(null);
  const { showToast } = useToast();

  // Snoozing or stopping takes the person off this list (nothing is due any more), so reload it.
  async function act(id: string, action: () => Promise<unknown>, done: string) {
    setBusy(id);
    try {
      await action();
      showToast({ description: done, variant: "success" });
      await loadFollowUps();
    } catch (err) {
      showToast({
        description: err instanceof Error ? err.message : "could not save that",
      });
    } finally {
      setBusy(null);
    }
  }

  const snooze = (item: FollowUpItem, days: string) =>
    act(
      item.id,
      () =>
        apiPost(`/contacts/${item.id}/follow-up/snooze`, {
          business_days: Number(days),
        }),
      `${item.full_name ?? "This person"} is snoozed.`,
    );

  const stop = (item: FollowUpItem) => {
    const update: ContactTrackingUpdate = {
      status: item.status === "follow_up_scheduled" ? "contacted" : item.status,
      next_follow_up_at: null,
      next_follow_up_channel: null,
    };
    return act(
      item.id,
      () => apiPatch(`/contacts/${item.id}/tracking`, update),
      `Follow-ups stopped for ${item.full_name ?? "this person"}.`,
    );
  };

  function loadFollowUps() {
    setError(null);
    return apiGet<FollowUpItem[]>("/contacts/follow-ups")
      .then(setItems)
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "failed to load follow-ups",
        ),
      );
  }

  useEffect(() => {
    loadFollowUps();
  }, []);

  if (error) {
    return (
      <div>
        <Card>
          <ErrorState message={error} onRetry={loadFollowUps} />
        </Card>
      </div>
    );
  }

  if (!items) {
    return (
      <div>
        <Card className="p-6">
          <SkeletonLines lines={6} />
        </Card>
      </div>
    );
  }

  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const rows = items.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

  return (
    <div>
      <Card className="p-0">
        {items.length === 0 ? (
          <EmptyState
            icon={ListChecks}
            title="Nothing due right now"
            description="People show up here on the day their next follow-up is due."
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Contact</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Where they are</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead>Last sent</TableHead>
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="whitespace-normal">
                      {item.full_name ?? "Unknown"}
                      {item.role_title && ` (${item.role_title})`}
                    </TableCell>
                    <TableCell>
                      <Link
                        to={`/companies/${item.company.id}`}
                        className="text-primary-text hover:underline"
                      >
                        {item.company.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {sequenceStatus(item.touches_sent).label}
                    </TableCell>
                    <TableCell>
                      {item.next_follow_up_at
                        ? dueLabel(item.next_follow_up_at)
                        : "Not set"}
                      {item.next_follow_up_channel && (
                        <span className="text-muted-foreground">
                          {" "}
                          by {CHANNEL_LABELS[item.next_follow_up_channel]}
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      {item.last_sent_at
                        ? formatDate(item.last_sent_at)
                        : "Never"}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        {!sequenceStatus(item.touches_sent).complete && (
                          <Button asChild size="sm">
                            <Link to={writeLink(item)}>Write follow-up</Link>
                          </Button>
                        )}
                        <SimpleSelect
                          label={`Snooze ${item.full_name ?? "this person"}`}
                          value=""
                          placeholder="Snooze"
                          options={SNOOZES}
                          onChange={(days) => void snooze(item, days)}
                          className="w-28"
                        />
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={busy === item.id}
                          onClick={() => void stop(item)}
                        >
                          Stop
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <TablePagination
              total={items.length}
              page={currentPage}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </>
        )}
      </Card>
    </div>
  );
}
