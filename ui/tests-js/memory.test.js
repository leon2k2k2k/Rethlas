import { describe, expect, it } from "vitest";
import "./setup.js";
import { renderMemoryChannels, renderValue } from "../static/js/memory.js";

describe("renderValue", () => {
  it("renders strings with math", () => {
    expect(renderValue("bound \\(n^2\\)")).toContain("\\(n^2\\)");
  });

  it("recurses into objects and arrays", () => {
    const html = renderValue({ plan: "p1", steps: ["a", { deep: "\\(x\\)" }] });
    expect(html).toContain("<strong>plan:</strong>");
    expect(html).toContain("<li>a</li>");
    expect(html).toContain("\\(x\\)");
  });

  it("escapes html in keys and primitives", () => {
    const html = renderValue({ "<k>": 5 });
    expect(html).toContain("&lt;k&gt;");
    expect(html).toContain("5");
  });

  it("handles null", () => {
    expect(renderValue(null)).toContain("null");
  });
});

describe("renderMemoryChannels", () => {
  it("orders channels and collapses events", () => {
    const blocks = renderMemoryChannels({
      events: [{ timestamp_utc: "2026-01-01T00:00:00Z", record: { e: 1 } }],
      branch_states: [{ timestamp_utc: "2026-01-01T00:00:00Z", record: { b: 1 } }],
    });
    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toContain("branch_states");
    expect(blocks[0]).toContain(" open");
    expect(blocks[1]).toContain("events");
    expect(blocks[1]).not.toContain(" open>");
  });
});
