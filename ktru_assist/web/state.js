"use strict";
// Правила применения ответов сервера (план, п. 7.2). Чистые функции: проверяются в node (tests/web/).
//  * ответ применяется только при совпадении session_id и revision;
//  * для одной revision результат B (submitted) не перезаписывается поздним черновиком A (draft);
//  * любое изменение ввода увеличивает revision — прежние вычисления становятся устаревшими;
//  * ответ, помеченный сервером stale, не применяется никогда.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KtruState = factory();
})(typeof self !== "undefined" ? self : this, function () {
  const STAGE_RANK = { draft: 0, submitted: 1 };

  function newSession() {
    const id = (Date.now().toString(36) + Math.random().toString(36).slice(2, 10)).slice(0, 16);
    return { sessionId: id, revision: 0, shown: null, pending: {}, lastInputAt: null };
  }

  function bump(s, now) {
    s.revision += 1;
    if (now !== undefined) s.lastInputAt = now;
    return s.revision;
  }

  function shouldApply(s, resp) {
    if (!resp || resp.stale) return false;
    if (resp.session_id !== s.sessionId || resp.revision !== s.revision) return false;
    if (s.shown && s.shown.revision === resp.revision &&
        STAGE_RANK[s.shown.stage] > STAGE_RANK[resp.stage]) return false;
    return true;
  }

  function markShown(s, resp) {
    s.shown = { revision: resp.revision, stage: resp.stage };
  }

  // editing | submitted | resolved | stale | provider_error
  function uiState(s, resp) {
    if (s.pending.submitted === s.revision) return "submitted";
    if (!resp) return "editing";
    if (resp.revision !== s.revision) return "stale";
    const llm = (resp.providers || []).find((p) => p.name === "llm");
    if (resp.stage === "submitted" && llm && (llm.status === "error" || llm.status === "timeout" ||
        llm.status === "invalid")) return "provider_error";
    if (resp.stage === "submitted") return "resolved";
    return "editing";
  }

  return { newSession, bump, shouldApply, markShown, uiState, STAGE_RANK };
});
