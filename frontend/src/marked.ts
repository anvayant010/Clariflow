/** Split the server's `marked_html` into plain text parts. We never put server HTML into the page. */
export interface MarkedParts {
  before: string;
  hit: string;
  after: string;
}

const ENTITIES: Record<string, string> = {
  "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#x27;": "'", "&#39;": "'", "&amp;": "&",
};

export function decodeEntities(s: string): string {
  return s.replace(/&(?:lt|gt|quot|#x27|#39|amp);/g, (m) => ENTITIES[m] ?? m);
}

export function parseMarked(html: string): MarkedParts {
  const m = /^([\s\S]*?)<mark>([\s\S]*?)<\/mark>([\s\S]*)$/.exec(html);
  if (!m) return { before: decodeEntities(html), hit: "", after: "" };
  return { before: decodeEntities(m[1]), hit: decodeEntities(m[2]), after: decodeEntities(m[3]) };
}
