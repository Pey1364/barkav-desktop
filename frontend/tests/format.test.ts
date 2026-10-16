import { describe, expect, it } from "vitest";
import { formatAmount, plainAmount } from "../src/lib/format";
import { withTimeout } from "../src/lib/async";

describe("amounts", () => {
  it("shows Persian digits with a separator every three digits", () => {
    expect(formatAmount("250000000")).toBe("۲۵۰٬۰۰۰٬۰۰۰");
    expect(formatAmount("۱۲۰۰")).toBe("۱٬۲۰۰");
    expect(formatAmount("")).toBe("");
  });

  it("sends plain digits only", () => {
    expect(plainAmount("۲۵۰٬۰۰۰")).toBe("250000");
  });
});

describe("withTimeout", () => {
  it("fails with the given message when the work takes too long", async () => {
    const never = new Promise<string>(() => undefined);
    await expect(withTimeout(never, 20, "Google did not answer")).rejects.toThrow("Google did not answer");
  });

  it("passes the result through when the work finishes in time", async () => {
    await expect(withTimeout(Promise.resolve("ok"), 1000, "late")).resolves.toBe("ok");
  });
});
