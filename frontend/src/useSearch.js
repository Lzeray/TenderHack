import { useCallback, useEffect, useRef, useState } from "react";
import { bump, markShown, newSession, shouldApply } from "./state.js";

const emptyParameters = () => ({ overrides: [], answers: [], corrections: {}, rejected: [], confirmed: [] });
async function post(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error("Не удалось получить ответ сервера. Попробуйте ещё раз.");
  return response.json();
}

export function useSearch() {
  const session = useRef(null);
  if (!session.current) session.current = newSession();
  const parameters = useRef(emptyParameters());
  // Скрытая строка «тип; ключ: значение» (docs/PARSE_INPUT_PLAN.md, P4): поиск идёт по ней, видимая строка — только
  // для ввода. Решения пользователя (ответы, выбор варианта, правки) хранятся в ней, пока их фрагмент есть в тексте.
  const canonical = useRef({ items: [] });
  const query = useRef("");
  const timers = useRef([]);
  const mounted = useRef(true);
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const resultRef = useRef(null);
  const [busy, setBusy] = useState({ fast: false, model: false });
  const [error, setError] = useState("");
  const [products, setProducts] = useState([]);
  const productKey = useRef("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [pageError, setPageError] = useState("");
  const [history, setHistory] = useState([]);
  const [revision, setRevision] = useState(0);

  const register = useCallback(() => {
    const s = session.current;
    bump(s, performance.now());
    setRevision(s.revision);
    post("/api/revision", { text: query.current, session_id: s.sessionId, revision: s.revision }).catch(() => {});
    return s.revision;
  }, []);
  const clearTimers = useCallback(() => { timers.current.forEach(clearTimeout); timers.current = []; }, []);

  const run = useCallback(async (stage = "draft", action = "search") => {
    if (!query.current.trim()) return;
    const s = session.current;
    const rev = s.revision;
    const input = query.current;
    const kind = stage === "draft" ? "fast" : "model";
    setBusy(previous => ({ ...previous, [kind]: true }));
    if (stage === "submitted") s.pending.submitted = rev;
    const sent = parameters.current;
    try {
      const data = await post("/api/search", { text: input, session_id: s.sessionId, revision: rev, stage, action, ...sent,
        canonical: canonical.current });
      if (!mounted.current || !shouldApply(s, data)) return;
      markShown(s, data);
      if (data.canonical) {
        canonical.current = data.canonical;
        // ответы и правки уже записаны в скрытую строку
        if (parameters.current === sent) parameters.current = { ...sent, overrides: [], answers: [] };
      }
      // Enter: в строке ввода исправляется только орфография
      if (stage === "submitted" && s.pending.enter === rev && data.corrected_text && query.current === input) {
        query.current = data.corrected_text;
        setText(data.corrected_text);
      }
      resultRef.current = data;
      setResult(data);
      setError("");
      const key = JSON.stringify([data.query?.original, data.query_profile, data.status]);
      if (key !== productKey.current) {
        productKey.current = key;
        setProducts(data.status === "conflict" ? [] : data.ste_results?.items || []);
        setPageError("");
      }
      const count = data.compatible_codes?.length ?? data.candidates?.filter(c => c.compatible && !c.is_template).length ?? 0;
      setHistory(previous => {
        let next = previous;
        const last = previous.at(-1);
        if (last && input !== last.text && !input.startsWith(last.text)) next = [];
        if (next.at(-1)?.count === count) return [...next.slice(0, -1), { text: input, count }];
        return [...next, { text: input, count }].slice(-7);
      });
    } catch (failure) {
      if (!mounted.current || rev !== s.revision) return;
      setError(stage === "submitted" && resultRef.current?.revision === rev
        ? "Дополнительный разбор недоступен. Быстрый поиск продолжает работать." : failure.message);
    } finally {
      if (s.pending.submitted === rev) delete s.pending.submitted;
      if (stage === "submitted" && s.pending.enter === rev) delete s.pending.enter;
      if (mounted.current && rev === s.revision) setBusy(previous => ({ ...previous, [kind]: false }));
    }
  }, []);

  const changeText = useCallback(value => {
    clearTimers();
    // текст меняется — решения пользователя не сбрасываются: сервер сверит их с фрагментами текста
    if (!value.trim()) { parameters.current = emptyParameters(); canonical.current = { items: [] }; }
    query.current = value;
    setText(value);
    setError("");
    setPageError("");
    setLoadingMore(false);
    setBusy({ fast: !!value.trim(), model: false });
    register();
    if (!value.trim()) {
      resultRef.current = null;
      setResult(null); setProducts([]); setHistory([]); productKey.current = "";
    } else {
      timers.current = [setTimeout(() => run("draft"), 200), setTimeout(() => run("submitted"), 1000)];
    }
  }, [clearTimers, register, run]);

  const submit = useCallback(() => {
    clearTimers();
    session.current.pending.enter = session.current.revision;
    run("draft"); run("submitted");
  }, [clearTimers, run]);
  const mutate = useCallback(update => {
    clearTimers();
    parameters.current = update(parameters.current);
    register();
    run("draft", "confirm"); run("submitted", "confirm");
  }, [clearTimers, register, run]);
  const override = useCallback(constraint => mutate(p => ({ ...p,
    overrides: [...p.overrides.filter(c => c.property !== constraint.property), constraint],
    answers: p.answers.filter(c => c.property !== constraint.property),
  })), [mutate]);
  const answer = useCallback(option => {
    const response = resultRef.current;
    const answers = option.answers?.length ? option.answers : option.answer ? [option.answer] : [];
    mutate(p => ({ ...p, answers: [...p.answers.filter(a => !answers.some(b => a.property === b.property)), ...answers],
      answers_query_hash: response.query_hash, rejected: [...p.rejected, ...(option.reject || [])],
      confirmed: [...p.confirmed, ...(option.confirm || [])] }));
  }, [mutate]);
  // Выбранный параметр записывается в строку поиска: «…, Тип каркаса: Металлический» — разбор читает точное название
  // свойства КТРУ. Фрагмент из описания (fragment) заменяется на месте, удаление вырезает его. Прежнее решение
  // о том же свойстве (ответ, выбор варианта) снимается из скрытой строки: теперь значение задаёт текст.
  const putInText = useCallback(({ name, fragment = null, phrase = "" }) => {
    const current = query.current;
    const at = fragment ? current.toLowerCase().indexOf(fragment.toLowerCase()) : -1;
    if (!phrase && at < 0) {   // фрагмента в тексте нет (значение из наименования или решение) — решение «удалить»
      mutate(p => ({ ...p, overrides: [...p.overrides.filter(c => c.property !== name), { property: name, remove: true }] }));
      return;
    }
    let next;
    if (at >= 0) {
      next = current.slice(0, at) + phrase + current.slice(at + fragment.length);
      if (!phrase) next = next.replace(/\s*[,;]\s*(?=[,;])/g, "").replace(/\s+([,;])/g, "$1").replace(/^[\s,;]+|[\s,;]+$/g, "").replace(/\s{2,}/g, " ");
    } else {
      next = `${current.trim().replace(/[\s,;]+$/, "")}, ${phrase}`;
    }
    const key = (name || "").toLowerCase().replaceAll("ё", "е");
    canonical.current = { ...canonical.current, items: (canonical.current.items || []).filter(i =>
      i.source === "text" || (i.key || "").toLowerCase().replaceAll("ё", "е") !== key) };
    clearTimers();
    query.current = next;
    setText(next);
    register();
    run("draft", "confirm"); run("submitted", "confirm");
  }, [clearTimers, mutate, register, run]);
  const correct = useCallback((original, value) => mutate(p => ({ ...p, corrections: { ...p.corrections, [original]: value } })), [mutate]);

  const loadMore = useCallback(async () => {
    const response = resultRef.current;
    if (!response || loadingMore) return;
    const rev = session.current.revision;
    const key = productKey.current;
    setLoadingMore(true); setPageError("");
    try {
      const page = await post("/api/products", { profile: response.query_profile, offset: products.length, limit: 25 });
      if (!mounted.current || rev !== session.current.revision || key !== productKey.current) return;
      setProducts(previous => { const ids = new Set(previous.map(p => p.id)); return [...previous, ...page.items.filter(p => !ids.has(p.id))]; });
    } catch (failure) {
      if (mounted.current && rev === session.current.revision) setPageError(failure.message);
    } finally {
      if (mounted.current && rev === session.current.revision) setLoadingMore(false);
    }
  }, [products.length, loadingMore]);

  useEffect(() => () => { mounted.current = false; clearTimers(); }, [clearTimers]);
  return { text, result, products, history, busy, error, pageError, loadingMore,
    stale: !!result && result.revision !== revision, changeText, submit, override, answer, correct, putInText, loadMore };
}
