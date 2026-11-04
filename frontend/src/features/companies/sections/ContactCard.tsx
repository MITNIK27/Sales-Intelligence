import { ExternalLink, Info, Mail, Phone, Trash2 } from "lucide-react";
import { useState } from "react";

import type {
  BuyingRole,
  CompanyDetail,
  Contact,
  ContactChannel,
  ContactRelevance,
  Product,
  RoleRelevanceResult,
} from "@/api/types";
import { SimpleSelect } from "@/components/SimpleSelect";
import { StatusTag } from "@/components/StatusTag";
import { ROLE_LABEL, ROLE_ORDER } from "@/features/brief/opportunityLabels";
import { NeedsReviewBadge, RolePriorityBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TRACKING_STATUS_LABELS } from "@/features/contacts/ContactTracking";
import type { SuggestedOffering } from "@/features/companies/lib/suggestedOfferings";
import { channelLink } from "@/features/companies/lib/contactLinks";
import { ContactOutreachPanel } from "@/features/outreach/ContactOutreachPanel";
import { cn } from "@/lib/utils";

// A person's part in the buying decision, from the buying committee. It is shown on the person's
// own card so the page has one list of people.
export type CommitteeInfo = {
  role: ContactRelevance | undefined;
  startHere: boolean;
  onOverride: (contactId: string, role: BuyingRole | "model") => void;
};

const CHIP: Record<BuyingRole | "unjudged", string> = {
  decision_maker: "bg-primary text-primary-foreground",
  influencer:
    "bg-secondary text-secondary-foreground ring-1 ring-foreground/20",
  user: "bg-muted text-foreground",
  not_relevant: "text-muted-foreground ring-1 ring-foreground/20",
  unjudged: "border border-dashed border-foreground/30 text-muted-foreground",
};

// What part this person plays. A word, never colour alone.
function RoleChip({ role }: { role: ContactRelevance | undefined }) {
  const key: BuyingRole | "unjudged" = role?.role ?? "unjudged";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center px-2 py-0.5 text-xs font-bold uppercase tracking-wide",
        CHIP[key],
      )}
    >
      {role?.role ? ROLE_LABEL[role.role] : "Role not judged yet"}
    </span>
  );
}

function RoleControl({
  contactId,
  name,
  role,
  onOverride,
}: {
  contactId: string;
  name: string;
  role: ContactRelevance | undefined;
  onOverride: CommitteeInfo["onOverride"];
}) {
  const human = role?.source === "human";
  return (
    <SimpleSelect
      label={`Role for ${name}`}
      placeholder="Change role"
      value={human ? (role?.role ?? "") : ""}
      options={[
        ...(human ? [{ value: "model", label: "Use the suggested role" }] : []),
        ...ROLE_ORDER.map((r) => ({ value: r, label: ROLE_LABEL[r] })),
      ]}
      onChange={(v) => onOverride(contactId, v as BuyingRole | "model")}
      className="h-10 w-44"
    />
  );
}

function initialsOf(name: string | null): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

// One way to reach the person: a link that opens in a new tab where the value is a web address
// or an email address, plain text otherwise.
function ChannelRow({ channel }: { channel: ContactChannel }) {
  const link = channelLink(channel);
  const Icon =
    channel.channel_type === "email"
      ? Mail
      : channel.channel_type === "phone"
        ? Phone
        : ExternalLink;
  const unchecked = channel.verification_status !== "verified";
  return (
    <li className="flex flex-wrap items-center gap-2 text-sm">
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      {link ? (
        <a
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium text-primary-text hover:underline"
        >
          {link.label}
          {channel.channel_type === "linkedin" && (
            <span className="sr-only"> (opens in a new tab)</span>
          )}
        </a>
      ) : (
        <span>{channel.value}</span>
      )}
      {unchecked && (
        <span className="text-xs text-muted-foreground">
          {channel.verification_status === "unverified"
            ? "not checked yet"
            : channel.verification_status}
        </span>
      )}
    </li>
  );
}

// Must sit inside a TooltipProvider (the contacts section provides one).
export function ContactCard({
  contact,
  company,
  roleRelevance,
  buyingRole,
  committee,
  products,
  researched,
  onConfirm,
  onRemove,
  onOutreachLogged,
}: {
  contact: Contact;
  company: CompanyDetail;
  roleRelevance: RoleRelevanceResult | undefined;
  buyingRole: ContactRelevance | undefined;
  // Set on the People tab once people have been ranked: shows the part they play, who to start
  // with, and a way to change the part.
  committee?: CommitteeInfo;
  products: Product[];
  researched: SuggestedOffering[];
  onConfirm: (contactId: string) => Promise<void>;
  onRemove: (contactId: string) => void;
  onOutreachLogged: (updated: Contact) => void;
}) {
  const [confirming, setConfirming] = useState(false);

  async function confirm() {
    setConfirming(true);
    await onConfirm(contact.id);
    setConfirming(false);
  }

  const part = committee ? committee.role : undefined;
  const suggestion = part?.source === "human" ? part.model_role : null;
  const why =
    part?.source === "human"
      ? suggestion
        ? `The suggested role was: ${ROLE_LABEL[suggestion]}.`
        : null
      : (part?.reasoning ?? null);
  const name = contact.full_name ?? "Unknown";
  const linkedin = contact.channels.find((c) => c.channel_type === "linkedin");
  const linkedinLink = linkedin ? channelLink(linkedin) : null;
  const otherChannels = contact.channels.filter((c) => c !== linkedin);

  return (
    <Card
      className={cn("gap-4", committee?.startHere && "ring-2 ring-primary")}
    >
      <div className="flex items-start gap-4 px-6">
        <div
          aria-hidden
          className="flex size-11 shrink-0 items-center justify-center bg-muted text-sm font-bold text-foreground"
        >
          {initialsOf(contact.full_name)}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-bold leading-tight">{name}</h3>
          {contact.role_title && (
            <p className="text-sm text-muted-foreground">
              {contact.role_title}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {committee && <RoleChip role={part} />}
            {committee?.startHere && (
              <StatusTag tone="good">Start here</StatusTag>
            )}
            {part?.source === "human" && (
              <StatusTag tone="neutral">Role changed by you</StatusTag>
            )}
            {part?.needs_review && part.source !== "human" && (
              <StatusTag tone="watch">Please check the role</StatusTag>
            )}
            {contact.needs_review && (
              <NeedsReviewBadge reason={contact.needs_review_reason} />
            )}
            {contact.status !== "not_contacted" && (
              <StatusTag tone="neutral">
                {TRACKING_STATUS_LABELS[contact.status]}
              </StatusTag>
            )}
            {!committee && buyingRole?.role && (
              <StatusTag tone="neutral">
                {`Buying role: ${ROLE_LABEL[buyingRole.role]}${buyingRole.source === "human" ? " (set by you)" : ""}`}
              </StatusTag>
            )}
            {roleRelevance && !part?.role && (
              <Tooltip>
                <TooltipTrigger className="cursor-default">
                  <RolePriorityBadge
                    priority={roleRelevance.priority}
                    label={roleRelevance.matched_category_name ?? undefined}
                  />
                </TooltipTrigger>
                <TooltipContent className="block max-w-sm whitespace-normal text-left">
                  {roleRelevance.reasoning}
                </TooltipContent>
              </Tooltip>
            )}
          </div>
          {why && <p className="mt-2 text-sm text-muted-foreground">{why}</p>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          {linkedinLink && (
            <Button asChild size="sm" variant="outline">
              <a
                href={linkedinLink.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                LinkedIn
                <ExternalLink className="size-4" aria-hidden />
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </Button>
          )}
          {contact.needs_review && (
            <Button
              type="button"
              className="text-sm font-semibold"
              onClick={confirm}
              disabled={confirming}
            >
              {confirming ? "Confirming…" : "Confirm contact"}
            </Button>
          )}
        </div>
      </div>

      {(otherChannels.length > 0 || (linkedin && !linkedinLink)) && (
        <ul className="flex flex-col gap-1 px-6">
          {[
            ...(linkedin && !linkedinLink ? [linkedin] : []),
            ...otherChannels,
          ].map((channel) => (
            <ChannelRow key={channel.id} channel={channel} />
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-3 border-t border-border px-6 pt-4">
        <ContactOutreachPanel
          contact={contact}
          companyId={company.id}
          companyNeedsReview={company.needs_review}
          products={products}
          researched={researched}
          onContactUpdated={onOutreachLogged}
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          {committee ? (
            <div className="flex items-center gap-2">
              <RoleControl
                contactId={contact.id}
                name={name}
                role={part}
                onOverride={committee.onOverride}
              />
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="About buying roles"
                    className="inline-flex size-8 items-center justify-center rounded-full border border-foreground/25 bg-card text-muted-foreground hover:border-primary hover:text-foreground"
                  >
                    <Info className="size-4" aria-hidden />
                  </button>
                </TooltipTrigger>
                <TooltipContent className="block max-w-xs whitespace-normal text-left">
                  Buying roles are guessed from job titles only. They show who
                  would decide, influence or use our lead offering, so you know
                  who to contact first. It is optional, and you can change any
                  role yourself.
                </TooltipContent>
              </Tooltip>
            </div>
          ) : (
            <span />
          )}
          <Button
            type="button"
            variant="destructive"
            className="text-sm font-semibold"
            onClick={() => {
              if (window.confirm(`Remove ${name}?`)) {
                onRemove(contact.id);
              }
            }}
          >
            <Trash2 aria-hidden />
            Remove contact
          </Button>
        </div>
      </div>
    </Card>
  );
}
