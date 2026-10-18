import { describe, expect, it } from "vitest";

import { websiteLabel, websiteUrl } from "@/lib/url";

describe("websiteUrl", () => {
  it("adds https to a bare domain", () => {
    expect(websiteUrl("dpd.com")).toBe("https://dpd.com");
    expect(websiteUrl("  dpd.com ")).toBe("https://dpd.com");
  });

  it("keeps an address that already has a scheme", () => {
    expect(websiteUrl("http://dpd.com/en")).toBe("http://dpd.com/en");
    expect(websiteUrl("HTTPS://dpd.com")).toBe("HTTPS://dpd.com");
  });

  it("never turns a script scheme into a link", () => {
    expect(websiteUrl("javascript:alert(1)")).toBe(
      "https://javascript:alert(1)",
    );
  });
});

describe("websiteLabel", () => {
  it("shows just the domain", () => {
    expect(websiteLabel("https://dpd.com/")).toBe("dpd.com");
    expect(websiteLabel("dpd.com")).toBe("dpd.com");
  });
});
