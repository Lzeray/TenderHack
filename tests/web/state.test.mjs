// Проверки правил применения ответов (план, п. 10.2). Запуск: node --test tests/web/
import { test } from "node:test";
import assert from "node:assert/strict";
import * as S from "../../frontend/src/state.js";

const resp = (s, revision, stage, extra = {}) => ({ session_id: s.sessionId, revision, stage, stale: false, ...extra });

test("ответ на старую revision не применяется", () => {
  const s = S.newSession();
  S.bump(s); S.bump(s);                       // revision 2
  assert.equal(S.shouldApply(s, resp(s, 1, "draft")), false);
  assert.equal(S.shouldApply(s, resp(s, 2, "draft")), true);
});

test("A для revision 10 после результата revision 11 игнорируется", () => {
  const s = S.newSession();
  for (let i = 0; i < 11; i++) S.bump(s);
  const r11 = resp(s, 11, "draft");
  assert.ok(S.shouldApply(s, r11)); S.markShown(s, r11);
  assert.equal(S.shouldApply(s, resp(s, 10, "draft")), false);
});

test("поздний A не перезаписывает B той же revision", () => {
  const s = S.newSession();
  S.bump(s);
  const b = resp(s, 1, "submitted");
  assert.ok(S.shouldApply(s, b)); S.markShown(s, b);
  assert.equal(S.shouldApply(s, resp(s, 1, "draft")), false);
});

test("ручная правка во время B делает ответ B устаревшим", () => {
  const s = S.newSession();
  S.bump(s);                                  // Enter на revision 1
  s.pending.submitted = 1;
  S.bump(s);                                  // правка → revision 2
  assert.equal(S.shouldApply(s, resp(s, 1, "submitted")), false);
});

test("ответ, помеченный сервером stale, не применяется", () => {
  const s = S.newSession();
  S.bump(s);
  assert.equal(S.shouldApply(s, resp(s, 1, "draft", { stale: true })), false);
});

test("чужой сеанс не применяется", () => {
  const s = S.newSession();
  S.bump(s);
  assert.equal(S.shouldApply(s, { ...resp(s, 1, "draft"), session_id: "other" }), false);
});

test("состояния интерфейса", () => {
  const s = S.newSession();
  S.bump(s);
  s.pending.submitted = 1;
  assert.equal(S.uiState(s, null), "submitted");
  s.pending = {};
  assert.equal(S.uiState(s, resp(s, 1, "submitted", { providers: [{ name: "llm", status: "timeout" }] })),
    "provider_error");
  assert.equal(S.uiState(s, resp(s, 1, "submitted", { providers: [{ name: "llm", status: "ok" }] })), "resolved");
  assert.equal(S.uiState(s, resp(s, 1, "draft")), "editing");
  S.bump(s);
  assert.equal(S.uiState(s, resp(s, 1, "draft")), "stale");
});
