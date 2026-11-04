import { useEffect, useState } from "react";

import { apiPost, apiPut } from "@/api/client";
import type { Product } from "@/api/types";
import { InfoTip } from "@/components/InfoTip";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  PROFILE_FIELDS,
  profileStatusLabel,
  profileToText,
  textToProfile,
  type ProfileFieldKey,
} from "@/features/products/buyerProfile";

// "Who buys this": the functions that decide on and influence an offering. It later decides which
// people at a prospect matter for it, so it is shown, editable, and clearly marked as generated or
// written by a person.
export function BuyerProfileEditor({
  product,
  onChanged,
}: {
  product: Product;
  onChanged: (product: Product) => void;
}) {
  const [text, setText] = useState(() => profileToText(product.buyer_profile));
  const [busy, setBusy] = useState<"generate" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setText(profileToText(product.buyer_profile));
  }, [product.buyer_profile]);

  async function run(kind: "generate" | "save") {
    setBusy(kind);
    setError(null);
    setSaved(false);
    try {
      const updated =
        kind === "generate"
          ? await apiPost<Product>(
              `/products/${product.id}/buyer-profile/generate`,
            )
          : await apiPut<Product>(
              `/products/${product.id}/buyer-profile`,
              textToProfile(text),
            );
      onChanged(updated);
      setSaved(kind === "save");
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setBusy(null);
    }
  }

  function generate() {
    if (
      product.buyer_profile &&
      !window.confirm("Replace the current profile with a newly generated one?")
    ) {
      return;
    }
    run("generate");
  }

  return (
    <Card className="mt-6">
      <CardContent>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-base font-bold">
              Who buys this
              <InfoTip label="About the buyer profile">
                Used to work out which people at a company matter for this
                offering, and which offerings fit a company. It describes
                business functions rather than job titles, because titles differ
                between companies. Edit anything that is wrong.
              </InfoTip>
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {profileStatusLabel(
                product.profile_status,
                product.profile_stale,
              )}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={generate}
            disabled={!!busy}
          >
            {busy === "generate" ? "Generating…" : "Generate from description"}
          </Button>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {PROFILE_FIELDS.map(({ key, label, hint }) => (
            <div key={key} className="flex flex-col gap-1.5">
              <Label htmlFor={`profile-${key}`}>{label}</Label>
              <Textarea
                id={`profile-${key}`}
                rows={4}
                value={text[key as ProfileFieldKey]}
                onChange={(e) => setText({ ...text, [key]: e.target.value })}
                placeholder="One per line"
              />
              <p className="text-xs text-muted-foreground">{hint}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Button type="button" onClick={() => run("save")} disabled={!!busy}>
            {busy === "save" ? "Saving…" : "Save profile"}
          </Button>
          {saved && (
            <span className="text-sm text-muted-foreground">Saved.</span>
          )}
          {error && <span className="text-sm text-destructive">{error}</span>}
        </div>
      </CardContent>
    </Card>
  );
}
