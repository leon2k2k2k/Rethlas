import { describe, expect, it } from "vitest";
import "./setup.js";
import { applyEvents, renderEvent } from "../static/js/transcript.js";

function container() {
  const div = document.createElement("div");
  div.className = "transcript";
  document.body.appendChild(div);
  return div;
}

describe("renderEvent", () => {
  it("assistant message renders markdown+math", () => {
    const html = renderEvent({ kind: "message", role: "assistant", text: "Proof of \\(x\\)" });
    expect(html).toContain("ev assistant");
    expect(html).toContain("\\(x\\)");
  });

  it("call card carries data-call-id and hidden result slot", () => {
    const html = renderEvent({ kind: "call", name: "exec", call_id: "call_9", args: "{}" });
    expect(html).toContain('data-call-id="call_9"');
    expect(html).toContain("running...");
  });

  it("unknown kinds render nothing", () => {
    expect(renderEvent({ kind: "mystery" })).toBe("");
  });
});

describe("applyEvents pairing", () => {
  it("joins output into its call card within one batch", () => {
    const c = container();
    applyEvents(c, [
      { kind: "call", name: "exec", call_id: "c1", args: "{}" },
      { kind: "output", call_id: "c1", text: "result!" },
    ]);
    const card = c.querySelector('[data-call-id="c1"]');
    expect(card.querySelector("pre.result").textContent).toBe("result!");
    expect(card.querySelector(".call-status").textContent).toContain("chars out");
    // no standalone output card
    expect(c.querySelectorAll(".ev.output")).toHaveLength(0);
  });

  it("joins output across batches (live tail)", () => {
    const c = container();
    applyEvents(c, [{ kind: "call", name: "exec", call_id: "c2", args: "{}" }]);
    applyEvents(c, [{ kind: "output", call_id: "c2", text: "late" }]);
    expect(c.querySelector('[data-call-id="c2"] pre.result').textContent).toBe("late");
  });

  it("orphan output renders standalone", () => {
    const c = container();
    applyEvents(c, [{ kind: "output", call_id: "nope", text: "orphan" }]);
    expect(c.querySelectorAll(".ev.output")).toHaveLength(1);
  });

  it("reports markdown presence", () => {
    const c = container();
    expect(applyEvents(c, [{ kind: "call", name: "x", call_id: "a", args: "" }])).toBe(false);
    expect(applyEvents(c, [{ kind: "reasoning", text: "hm" }])).toBe(true);
  });
});
