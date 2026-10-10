// Shared revision rules: an older request must never replace the current result.
export const STAGE_RANK = { draft: 0, submitted: 1 };
export function newSession() {
  const sessionId = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return { sessionId, revision: 0, shown: null, pending: {}, lastInputAt: null };
}
export function bump(session, now) {
  session.revision += 1;
  session.lastInputAt = now;
  return session.revision;
}
export function shouldApply(session, response) {
  return !!response && !response.stale && response.session_id === session.sessionId &&
    response.revision === session.revision && !(session.shown?.revision === response.revision &&
      STAGE_RANK[session.shown.stage] > STAGE_RANK[response.stage]);
}
export function markShown(session, response) {
  session.shown = { revision: response.revision, stage: response.stage };
}
export function uiState(session, response) {
  if (session.pending.submitted === session.revision) return "submitted";
  if (!response) return "editing";
  if (response.revision !== session.revision) return "stale";
  if (response.stage === "submitted" && response.providers?.some(p =>
    ["llm", "qwen"].includes(p.name) && ["error", "timeout", "invalid"].includes(p.status))) return "provider_error";
  return response.stage === "submitted" ? "resolved" : "editing";
}
export function parseConstraint(property, raw, unit) {
  const text = raw.trim().replaceAll(",", ".");
  const range = text.match(/^(-?\d+(?:\.\d+)?)\s*[–-]\s*(-?\d+(?:\.\d+)?)$/);
  if (range) return { property, op: "between", value: range[1], value_to: range[2], unit: unit || null };
  for (const [pattern, op] of [[/^(≥|>=)\s*/, "ge"], [/^(≤|<=)\s*/, "le"], [/^>\s*/, "gt"], [/^<\s*/, "lt"], [/^(≠|!=|не )\s*/, "ne"]]) {
    if (pattern.test(text)) return { property, op, value: text.replace(pattern, ""), unit: unit || null };
  }
  return { property, op: "eq", value: text, unit: unit || null };
}
export function featureValue(feature) {
  if (feature.op === "between") return `${feature.value}–${feature.value_to}`;
  if (feature.op === "in") return (feature.values || []).join(" / ");
  return ({ ne: "не ", ge: "≥ ", gt: "> ", le: "≤ ", lt: "< " }[feature.op] || "") + (feature.value ?? "");
}
