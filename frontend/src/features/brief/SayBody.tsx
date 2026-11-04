import type { Recommendation } from "@/api/types";

// What to say: the pitch, why this company, and the talking points. Written once per version of
// the research, so asking again does not spend another model call.
export function SayBody({
  recommendation,
}: {
  recommendation: Recommendation | null;
}) {
  if (!recommendation) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing written yet. Use the button above to write the message for the
        lead offering.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="text-base font-medium">{recommendation.pitch_summary}</p>
      <p className="text-sm text-muted-foreground">
        {recommendation.why_this_company}
      </p>
      {recommendation.talking_points.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-bold">Talking points</h3>
          <ul className="list-inside list-disc text-sm">
            {recommendation.talking_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
