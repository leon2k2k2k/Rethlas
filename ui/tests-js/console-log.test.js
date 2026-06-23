import { describe, expect, it } from "vitest";
import "./setup.js";
import { renderConsoleLog, trimLogPreamble } from "../static/js/console-log.js";

const SAMPLE = `OpenAI Codex v0.137.0
--------
model: gpt-5.5
session id: 019ea7f8-d79e-7353-b90a-67b6037dc995
--------
user
Verify the proof of \\(n+0=n\\).
codex
I will check the statement sequentially; the key risk is the \\(\\epsilon_K\\) descent.
exec
/bin/bash -lc "sed -n '1,220p' skills/verify.md" in /home/x
 succeeded in 0ms:
contents here with $VAR
codex
The sequential check found no defects.
tokens used
12,345
`;

describe("renderConsoleLog", () => {
  it("splits sections into cards", () => {
    const html = renderConsoleLog(SAMPLE);
    expect(html.match(/ev assistant/g)).toHaveLength(2);
    expect(html).toContain("user message (");
    expect(html).toContain("→ exec /bin/bash");
    expect(html).toContain("tokens used: 12,345");
  });

  it("renders codex messages as markdown with math preserved", () => {
    const html = renderConsoleLog(SAMPLE);
    expect(html).toContain("\\(\\epsilon_K\\)");
  });

  it("keeps banner block as monospace head", () => {
    const html = renderConsoleLog(SAMPLE);
    expect(html).toContain("session id: 019ea7f8");
  });

  it("breaks shell dollars inside exec output", () => {
    const html = renderConsoleLog(SAMPLE);
    expect(html).toContain("$​VAR");
  });

  it("exec cards are open by default", () => {
    const html = renderConsoleLog(SAMPLE);
    expect(html).toContain('<details class="ev call" open>');
  });
});

describe("trimLogPreamble", () => {
  it("cuts everything before the codex banner", () => {
    const log = "started_at: x\ncommand: codex exec 'huge prompt'\n" + SAMPLE;
    expect(trimLogPreamble(log).startsWith("OpenAI Codex v")).toBe(true);
  });

  it("returns text unchanged when no banner", () => {
    expect(trimLogPreamble("plain")).toBe("plain");
  });
});
