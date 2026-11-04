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
  if (location.trim()) {
    seeds.push({
      id: newRequirementId(),
      name: "Operates in the target location",
      description: `The company has its headquarters or significant operations in ${location.trim()}.`,
      include: true,
      mustHave: true,
    });
  }
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
