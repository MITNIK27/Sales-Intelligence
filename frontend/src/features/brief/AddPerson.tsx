import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { addPerson } from "@/features/brief/api";
import {
  EMPTY_PERSON,
  validatePerson,
  type PersonErrors,
  type PersonForm,
} from "@/features/brief/personForm";

const FIELDS: {
  key: keyof PersonForm;
  label: string;
  hint?: string;
  placeholder: string;
  required?: boolean;
}[] = [
  { key: "fullName", label: "Name", placeholder: "Jane Doe", required: true },
  {
    key: "roleTitle",
    label: "Job title",
    hint: "Their role is judged from this.",
    placeholder: "Chief Technology Officer",
    required: true,
  },
  {
    key: "linkedinUrl",
    label: "LinkedIn profile",
    placeholder: "linkedin.com/in/jane-doe",
  },
  { key: "email", label: "Email", placeholder: "jane@company.com" },
];

// Adds someone the rep knows works at the company, for when the people search finds no one
// useful. The new person is judged for their part in the buying decision straight after.
export function AddPerson({
  companyId,
  onAdded,
}: {
  companyId: string;
  onAdded: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<PersonForm>(EMPTY_PERSON);
  const [errors, setErrors] = useState<PersonErrors>({});
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  if (!open) {
    return (
      <Button variant="action" onClick={() => setOpen(true)}>
        Add a person
      </Button>
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = validatePerson(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setSaving(true);
    setFailure(null);
    try {
      await addPerson(companyId, {
        full_name: form.fullName.trim(),
        role_title: form.roleTitle.trim(),
        linkedin_url: form.linkedinUrl.trim() || null,
        email: form.email.trim() || null,
      });
      setForm(EMPTY_PERSON);
      setOpen(false);
      await onAdded();
    } catch (err) {
      setFailure(
        err instanceof Error && !err.message.includes("[object")
          ? err.message
          : "Could not add this person.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      className="mt-1 w-full basis-full border border-border bg-card p-4"
      aria-label="Add a person"
    >
      <h3 className="mb-3 text-sm font-bold">Add a person</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <div key={f.key} className="flex flex-col gap-1">
            <label htmlFor={`person-${f.key}`} className="text-sm font-medium">
              {f.label}
              {!f.required && (
                <span className="font-normal text-muted-foreground">
                  {" "}
                  (optional)
                </span>
              )}
            </label>
            <Input
              id={`person-${f.key}`}
              value={form[f.key]}
              placeholder={f.placeholder}
              aria-invalid={!!errors[f.key]}
              aria-describedby={
                errors[f.key] ? `person-${f.key}-error` : undefined
              }
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
            />
            {errors[f.key] ? (
              <p
                id={`person-${f.key}-error`}
                className="text-xs text-destructive"
              >
                {errors[f.key]}
              </p>
            ) : (
              f.hint && (
                <p className="text-xs text-muted-foreground">{f.hint}</p>
              )
            )}
          </div>
        ))}
      </div>
      {failure && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {failure}
        </p>
      )}
      <div className="mt-4 flex gap-2">
        <Button type="submit" disabled={saving}>
          {saving ? "Adding…" : "Add person"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={saving}
          onClick={() => {
            setOpen(false);
            setErrors({});
            setFailure(null);
          }}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
