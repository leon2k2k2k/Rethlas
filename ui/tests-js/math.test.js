import { describe, expect, it } from "vitest";
import "./setup.js";
import {
  escapeConsoleText, renderMath, renderMathInline, restoreMath, shieldMath,
} from "../static/js/math.js";

describe("shieldMath / restoreMath", () => {
  it("round-trips inline TeX through markdown untouched", () => {
    const src = "Let \\(P \\subset \\mathbb{R}^2\\) be finite.";
    const html = renderMath(src);
    expect(html).toContain("\\(P \\subset \\mathbb{R}^2\\)");
  });

  it("round-trips display TeX with markdown-hostile content", () => {
    const src = "Define\n\\[\nE_1(P) = \\#\\{\\{p,q\\}: \\|p-q\\|_2 = 1\\}\n\\]\ndone.";
    const html = renderMath(src);
    expect(html).toContain("\\|p-q\\|_2 = 1");
    // underscores inside math must not become <em>
    expect(html).not.toContain("<em>2 = 1");
  });

  it("handles $$ display math", () => {
    const html = renderMath("$$a_1 + a_2$$");
    expect(html).toContain("$$a_1 + a_2$$");
  });

  it("handles single-dollar inline math", () => {
    const html = renderMath("price is $x_1$ here");
    expect(html).toContain("$x_1$");
  });

  it("does not treat spaced dollars as math", () => {
    const { stash } = shieldMath("costs $5 and then $ 6");
    expect(stash).toEqual([]);
  });

  it("escapes HTML inside restored math", () => {
    const html = renderMath("\\(a < b\\)");
    expect(html).toContain("a &lt; b");
    expect(html).not.toContain("a < b\\)");
  });

  it("markdown still works around math", () => {
    const html = renderMath("## Head\n\n**bold** and \\(x\\)");
    expect(html).toContain("<h2");
    expect(html).toContain("<strong>bold</strong>");
  });

  it("renderMathInline produces no paragraph wrapper", () => {
    const html = renderMathInline("just **text** with \\(x\\)");
    expect(html).not.toContain("<p>");
    expect(html).toContain("<strong>text</strong>");
  });

  it("restoreMath escapes stash content", () => {
    expect(restoreMath(" MATH0 ", ["<script>"])).toBe("&lt;script&gt;");
  });
});

describe("escapeConsoleText", () => {
  it("breaks $ pairing for shell variables", () => {
    const out = escapeConsoleText("echo $FOO and $BAR");
    expect(out).not.toMatch(/\$FOO and \$BAR/);
    expect(out).toContain("$​FOO");
  });

  it("escapes HTML", () => {
    expect(escapeConsoleText("<b>")).toBe("&lt;b&gt;");
  });

  it("leaves backslash-paren math intact for MathJax", () => {
    expect(escapeConsoleText("check \\(n+0=n\\)")).toContain("\\(n+0=n\\)");
  });
});
