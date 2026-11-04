import { useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Tabs, type TabItem } from "@/components/Tabs";
import { FollowUpsPage } from "@/features/contacts/FollowUpsPage";
import { DraftsPage } from "@/features/drafts/DraftsPage";

type View = "drafts" | "follow-ups";

// Everything about reaching people in one place. Today that is the messages written for you and
// the follow-ups that are due; sent mail, replies and logged outreach join here once mail is linked.
const VIEWS: TabItem<View>[] = [
  { id: "drafts", label: "Drafts" },
  { id: "follow-ups", label: "Follow-ups" },
];

const DESCRIPTION: Record<View, string> = {
  drafts:
    "Every message the system has written for you. Review it, edit it, then copy it out and mark it sent, or discard it.",
  "follow-ups": "People whose next follow-up date is today or in the past.",
};

export function OutreachPage() {
  const [params, setParams] = useSearchParams();
  const view: View =
    params.get("view") === "follow-ups" ? "follow-ups" : "drafts";

  return (
    <div>
      <PageHeader title="Outreach" description={DESCRIPTION[view]} />
      <Tabs
        label="Outreach sections"
        tabs={VIEWS}
        active={view}
        onChange={(id) => setParams({ view: id }, { replace: true })}
      />
      {view === "drafts" ? <DraftsPage /> : <FollowUpsPage />}
    </div>
  );
}
