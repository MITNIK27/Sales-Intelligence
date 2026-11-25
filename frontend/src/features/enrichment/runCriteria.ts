import { describePlaces, splitPlaces } from "@/features/enrichment/places";

// The criteria a person types for one Market Discovery search. Each can also be a "must have" for
// this search, which drops a company that clearly fails it; every company the search finds also
// keeps the criteria on its page. With nothing ticked nothing is excluded.

export type Requirement = {
  id: string;
  name: string;
  description: string;
  include: boolean;
  mustHave: boolean;
};

// What the server accepts for one chosen criterion.
export type RunCriterionRequest = {
  name?: string | null;
  description?: string | null;
  must_have: boolean;
};

let counter = 0;
export function newRequirementId(): string {
  counter += 1;
  return `req-${Date.now()}-${counter}`;
}

// Starting points built from what the search was parsed into. Industry and location are on by
// default, as must-haves; size is offered but off, because employee counts are often missing from
// the data and an unverifiable must-have would leave a company "needs evidence" instead of passing.
export function seedRequirements(
  industryKeywords: string,
  location: string,
  employeeSizeRange: string,
): Requirement[] {
  const seeds: Requirement[] = [];
  if (industryKeywords.trim()) {
    seeds.push({
      id: newRequirementId(),
      name: "Operates in the target industry",
      description: `The company's main business is in: ${industryKeywords.trim()}.`,
      include: true,
      mustHave: true,
    });
  }
  const places = splitPlaces(location);
  if (places.length > 0) seeds.push(locationRequirement(places));
  if (employeeSizeRange.trim()) {
    seeds.push({
      id: newRequirementId(),
      name: "Company size in range",
      description: `The company has about ${employeeSizeRange.trim()} employees.`,
      include: false,
      mustHave: false,
    });
  }
  return seeds;
}

const LOCATION_NAME = "Operates in the target location";

export function locationDescription(places: string[]): string {
  return `The company has its headquarters or significant operations in ${describePlaces(places)}.`;
}

function locationRequirement(places: string[]): Requirement {
  return {
    id: newRequirementId(),
    name: LOCATION_NAME,
    description: locationDescription(places),
    include: true,
    mustHave: true,
  };
}

// Keeps the location check in step with the places chosen, so adding France after the search was
// read does not leave a must-have that still says Germany only. A check the person has edited is
// left alone; the automatic one is updated, added when the first place is added, and removed when
// the last place is.
export function syncLocationRequirement(
  requirements: Requirement[],
  before: string[],
  after: string[],
): Requirement[] {
  const index = requirements.findIndex(
    (r) =>
      r.name === LOCATION_NAME &&
      r.description === (before.length ? locationDescription(before) : ""),
  );
  if (index === -1) {
    const anyLocation = requirements.some((r) => r.name === LOCATION_NAME);
    return before.length === 0 && after.length > 0 && !anyLocation
      ? [...requirements, locationRequirement(after)]
      : requirements;
  }
  if (after.length === 0) return requirements.filter((_, i) => i !== index);
  return requirements.map((r, i) =>
    i === index ? { ...r, description: locationDescription(after) } : r,
  );
}

export function toRequestCriteria(
  requirements: Requirement[],
): RunCriterionRequest[] {
  return requirements
    .filter((r) => r.include && r.name.trim())
    .map((r) => ({
      name: r.name.trim(),
      description: r.description.trim() || null,
      must_have: r.mustHave,
    }));
}

// A one-line summary of what will be applied, shown above the Start button.
export function criteriaSummary(requirements: Requirement[]): string {
  const chosen = toRequestCriteria(requirements);
  if (chosen.length === 0)
    return "No criteria chosen. Companies will be ranked by how well our offerings fit, and none will be dropped.";
  const must = chosen.filter((c) => c.must_have).length;
  return `${chosen.length} criteri${chosen.length === 1 ? "on" : "a"} chosen, ${must} of them must-have.`;
}
