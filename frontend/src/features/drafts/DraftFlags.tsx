/** Figures or past-work claims in a draft that the research did not contain. It only warns: the
 * rep reads the email before sending either way. */
export function DraftFlags({ flags }: { flags?: string[] | null }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div
      role="note"
      className="border border-border bg-chip-warning-bg px-3 py-2 text-sm text-chip-warning-fg"
    >
      <p className="font-medium">Check before sending</p>
      <ul className="mt-1 list-disc pl-5">
        {flags.map((flag) => (
          <li key={flag}>{flag}</li>
        ))}
      </ul>
    </div>
  );
}
