import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

test("bundled fictional Contexts agree with the versioned contract fixtures", () => {
  const source = JSON.parse(
    readFileSync(
      new URL(
        "../../docs/contracts/examples/core-contexts.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const bundled = JSON.parse(
    readFileSync(new URL("../src/core-contexts.json", import.meta.url), "utf8"),
  );
  expect(bundled.cases).toEqual(
    source.cases.map((item: { name: string; context: unknown }) => ({
      name: item.name,
      context: item.context,
    })),
  );
});
