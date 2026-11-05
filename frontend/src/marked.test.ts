import { describe, expect, it } from "vitest";
import { decodeEntities, parseMarked } from "./marked";

describe("parseMarked", () => {
  it("splits around the highlighted quote", () => {
    expect(parseMarked("P-12 <mark>pressure 50</mark> unit")).toEqual({ before: "P-12 ", hit: "pressure 50", after: " unit" });
  });
  it("decodes escaped text and never returns markup", () => {
    const p = parseMarked("a &lt;script&gt; &amp; <mark>b &quot;q&quot;</mark>");
    expect(p.before).toBe("a <script> & ");
    expect(p.hit).toBe('b "q"');
  });
  it("handles a transcript with no highlight", () => {
    expect(parseMarked("just text")).toEqual({ before: "just text", hit: "", after: "" });
  });
  it("does not double-decode", () => {
    expect(decodeEntities("&amp;lt;")).toBe("&lt;");
  });
});
