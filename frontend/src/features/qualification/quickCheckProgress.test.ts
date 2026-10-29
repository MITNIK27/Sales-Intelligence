import { describe, expect, it } from "vitest";

import {
  elapsedLabel,
  quickCheckSteps,
  stepStates,
} from "@/features/qualification/quickCheckProgress";

describe("quick check progress", () => {
  it("adds a step for the focus only when there is one", () => {
    expect(quickCheckSteps(null)).toHaveLength(2);
    const withFocus = quickCheckSteps("payments");
    expect(withFocus).toHaveLength(3);
    expect(withFocus[1]).toBe("Looking for evidence about payments");
  });

  it("marks finished, current and waiting steps from the job progress", () => {
    expect(stepStates(3, null)).toEqual(["current", "waiting", "waiting"]);
    expect(stepStates(3, { done: 1, total: 3 })).toEqual(["done", "current", "waiting"]);
    expect(stepStates(2, { done: 2, total: 2 })).toEqual(["done", "done"]);
  });

  it("formats elapsed time as minutes and seconds", () => {
    expect(elapsedLabel(0, 65_000)).toBe("1:05");
    expect(elapsedLabel(10_000, 5_000)).toBe("0:00");
  });
});
