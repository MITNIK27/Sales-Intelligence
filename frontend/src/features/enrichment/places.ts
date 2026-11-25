// The places a Market Discovery search looks in. The server takes them as one `location` string
// separated by "; " (a comma is not used, because "Pune, India" is one place); the server searches
// each place on its own.

export const MAX_PLACES = 5;
const SEPARATOR = ";";

function tidy(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function splitPlaces(location: string | null | undefined): string[] {
  const out: string[] = [];
  for (const part of (location ?? "").split(SEPARATOR)) {
    const place = tidy(part);
    if (place && !out.some((p) => p.toLowerCase() === place.toLowerCase()))
      out.push(place);
  }
  return out.slice(0, MAX_PLACES);
}

export function joinPlaces(places: string[]): string {
  return places.map(tidy).filter(Boolean).join(`${SEPARATOR} `);
}

// Adds a typed place unless it is blank, a repeat (ignoring case), or the limit is reached.
export function addPlace(places: string[], text: string): string[] {
  const place = tidy(text)
    .replace(/[,;]+$/, "")
    .trim();
  if (!place || places.length >= MAX_PLACES) return places;
  if (places.some((p) => p.toLowerCase() === place.toLowerCase()))
    return places;
  return [...places, place];
}

export function removePlace(places: string[], place: string): string[] {
  return places.filter((p) => p !== place);
}

// "Germany", "Germany or France", "Germany, France or Pune".
export function describePlaces(places: string[]): string {
  if (places.length <= 1) return places[0] ?? "";
  return `${places.slice(0, -1).join(", ")} or ${places[places.length - 1]}`;
}
