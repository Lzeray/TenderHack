# Полный набор метрик бенчмарка `main` (10.10.2026)

Все метрики из `benchmark/README.md` (общий набор, ранжирование и вопросы) и `benchmark/independent/README.md` (метрики v2, доверительные интервалы, тривиальные базовые линии) по **всем** наборам, которые есть в `main`: 16 наборов `benchmark.run` (4 общих + 11 метаморфных + стресс-набор `experiments/suites/stress.jsonl`) и 14 наборов v2.

- Код бенчмарка — `benchmark/` из `main` `33751bb` (не менялся с `86ef95f`, кроме адаптера `ktru.py` и набора `lazy_numbers`). Адаптер `ktru:core` (ядро без моделей), реальный снимок `nsiKTRUNew_all_actual_20261003020003`.
- `benchmark.run`: `--dialog --repeat 2` (детерминизм — доля совпавших ответов на повторе).
- `benchmark.independent.run`: диалог k ≤ 3, бутстреп 2000, базовые линии включены, test-кейсы скрыты.
- `main` `33751bb` = `matvey_develop` + React-интерфейс Айдара; ядро то же, что в `d96d441`.
- Колонки: текущий `main`, ветки `Lenaz` и `aydar`, MVP — старый `main` до слияния.

Как читать (порядок из `benchmark/README.md`): сначала безопасность (`auto_incorrect`, `forbidden_*`, `wrong_auto` — меньше), затем полезность (`pass_rate`, `required_auto_hit`, `auto_coverage`), затем ранжирование, диалог и задержка.

## 0. Сводка

#### Ключевые числа

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `natural test: wrong_auto` | 5 | 1 | 4 | 6 |
| `natural test: auto_precision` | 0.963 | 0.993 | 0.966 | 0.949 |
| `natural test: code_reached@0` | 0.418 | 0.451 | 0.358 | 0.355 |
| `natural test: code_reached@2` | 0.844 | 0.821 | 0.783 | 0.776 |
| `natural test: required_hit` | 0.693 | 0.746 | 0.593 | 0.577 |
| `natural test: hit@1` | 0.895 | 0.907 | 0.859 | 0.853 |
| `natural test: mrr` | 0.919 | 0.917 | 0.891 | 0.882 |
| `natural test: useless_question_rate` | 0.578 | 0.64 | 0.611 | 0.626 |
| `contradictions test: no_code_respected` | 0.941 | 0.98 | 0.912 | 0.941 |
| `out_of_scope test: no_code_respected` | 1 | 1 | 1 | 1 |
| `метаморфные (all): wrong_auto, сумма` | 105 | 77 | 113 | 107 |
| `v1, все наборы: auto_incorrect, сумма` | 105 | 78 | 114 | 110 |
| `v1, все наборы: forbidden_auto_violations, сумма` | 117 | 144 | 146 | 150 |
| `v1, все наборы: forbidden_code_hits, сумма` | 104 | 75 | 111 | 103 |
| `v1 stress: pass_rate` | 1 | 0.956 | 0.956 | 0.939 |
| `v1, все наборы: errors (исключения)` | 0 | 0 | 0 | 0 |
| `v1, все наборы: determinism, минимум` | 1 | 1 | 1 | 1 |

## 1. `benchmark.run`: метрики общего набора, ранжирование и вопросы

Определения — `benchmark/README.md`, разделы «Метрики» и «Ранжирование и вопросы». `*_by_step` — после 0, 1, 2… ответов на вопросы.

#### behaviour (18 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 18 | 18 | 18 | 18 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 7, conflict: 3, matched: 6, not_found: 2 | clarification: 7, conflict: 3, matched: 6, not_found: 2 | clarification: 7, conflict: 3, matched: 6, not_found: 2 | clarification: 8, conflict: 3, matched: 5, not_found: 2 |
| `pass_rate` | 1 | 1 | 1 | 0.833 |
| `status_accuracy` | 1 | 1 | 1 | 1 |
| `auto_coverage` | 0.333 | 0.333 | 0.333 | 0.278 |
| `auto_correct` | 6 | 6 | 6 | 5 |
| `auto_incorrect` | 0 | 0 | 0 | 0 |
| `auto_precision` | 1 | 1 | 1 | 1 |
| `error_upper95` | 0.5 | 0.5 | 0.5 | 0.6 |
| `required_auto_hit` | 1 | 1 | 1 | 1 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 0 |
| `forbidden_code_hits` | 0 | 0 | 0 | 0 |
| `compatible_recall` | 1 | 1 | 1 | 1 |
| `checks_pass` | 1 | 1 | 1 | 0.75 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 |
| `checks.warning` | 3 / 3 | 3 / 3 | 3 / 3 | 0 / 3 |
| `checks.no_feature` | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 |
| `checks.subset_of` | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |
| `dialog_resolved` | 1 | 1 | 1 | 1 |
| `dialog_cases` | 6 | 6 | 6 | 7 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.83 | 1.83 | 1.83 | 1.71 |
| `latency_ms.p50` | 5.84 | 6.62 | 16.17 | 4.74 |
| `latency_ms.p95` | 20.99 | 19.97 | 34.72 | 11.22 |
| `latency_ms.max` | 77.15 | 21.07 | 88.47 | 21.17 |
| `latency_ms.mean` | 11.48 | 8.36 | 22.36 | 6.18 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0 | 0 | 0 | 0 |
| `ranking.ranked_cases` | 12 | 12 | 12 | 12 |
| `ranking.hit@1` | 1 | 1 | 0.917 | 0.917 |
| `ranking.hit@3` | 1 | 1 | 1 | 1 |
| `ranking.hit@5` | 1 | 1 | 1 | 1 |
| `ranking.mrr` | 1 | 1 | 0.958 | 0.958 |
| `ranking.ndcg@3` | 1 | 1 | 0.969 | 0.969 |
| `ranking.type_hit@1` | 1 | 1 | 1 | 1 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0 | 0 | 0 | 0 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 1 | 1 | 0.958 | 0.958 |
| `ranking.dialog_traced` | 12 | 12 | 12 | 12 |
| `ranking.mrr_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 0.958 → 1 → 1 → 1 → 1 → 1 → 1 | 0.958 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.hit1_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 0.917 → 1 → 1 → 1 → 1 → 1 → 1 | 0.917 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.rank_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1.08 → 1 → 1 → 1 → 1 → 1 → 1 | 1.08 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 1 | 1 | 1 | 1 |
| `ranking.questions_to_top1_mean` | 0 | 0 | 0.08 | 0.08 |
| `ranking.bits_per_question` | 0 | 0 | 0.091 | 0.083 |
| `ranking.useless_question_rate` | 1 | 1 | 0.909 | 0.917 |
| `ranking.dead_end_rate` | 0 | 0 | 0 | 0 |

#### manual_dev (28 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 28 | 28 | 28 | 28 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 8, conflict: 2, matched: 17, not_found: 1 | clarification: 8, conflict: 2, matched: 17, not_found: 1 | clarification: 12, conflict: 2, matched: 13, not_found: 1 | clarification: 9, conflict: 2, matched: 16, not_found: 1 |
| `pass_rate` | 1 | 1 | 0.857 | 1 |
| `status_accuracy` | 1 | 1 | 0.857 | 1 |
| `auto_coverage` | 0.607 | 0.607 | 0.464 | 0.571 |
| `auto_correct` | 17 | 17 | 13 | 16 |
| `auto_incorrect` | 0 | 0 | 0 | 0 |
| `auto_precision` | 1 | 1 | 1 | 1 |
| `error_upper95` | 0.176 | 0.176 | 0.231 | 0.188 |
| `required_auto_hit` | 1 | 1 | 0.75 | 1 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 0 |
| `forbidden_code_hits` | 0 | 0 | 0 | 0 |
| `compatible_recall` | 1 | 1 | 1 | 1 |
| `checks_pass` | — | — | — | — |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_resolved` | 1 | 1 | 0.889 | 1 |
| `dialog_cases` | 5 | 5 | 9 | 6 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.8 | 1.8 | 1.5 | 1.67 |
| `latency_ms.p50` | 6.89 | 6.82 | 16.85 | 6.01 |
| `latency_ms.p95` | 26.45 | 19.01 | 34.8 | 67.72 |
| `latency_ms.max` | 62.86 | 73.83 | 69.34 | 76.07 |
| `latency_ms.mean` | 10.21 | 8.88 | 16.78 | 10.9 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0 | 0 | 0.25 | 0 |
| `ranking.ranked_cases` | 22 | 22 | 22 | 22 |
| `ranking.hit@1` | 1 | 1 | 1 | 0.955 |
| `ranking.hit@3` | 1 | 1 | 1 | 1 |
| `ranking.hit@5` | 1 | 1 | 1 | 1 |
| `ranking.mrr` | 1 | 1 | 1 | 0.977 |
| `ranking.ndcg@3` | 1 | 1 | 1 | 0.983 |
| `ranking.type_hit@1` | 1 | 1 | 1 | 1 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0 | 0 | 0 | 0 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.977 | 0.977 | 0.89 | 0.955 |
| `ranking.dialog_traced` | 22 | 22 | 22 | 22 |
| `ranking.mrr_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 0.977 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.hit1_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 0.955 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.rank_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1.05 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 1 | 1 | 1 | 1 |
| `ranking.questions_to_top1_mean` | 0 | 0 | 0 | 0.05 |
| `ranking.bits_per_question` | 0.111 | 0.111 | 0.359 | 0.2 |
| `ranking.useless_question_rate` | 0.889 | 0.889 | 0.778 | 0.8 |
| `ranking.dead_end_rate` | 0 | 0 | 0 | 0 |

#### manual_holdout (18 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 18 | 18 | 18 | 18 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 3, conflict: 1, matched: 13, not_found: 1 | clarification: 3, conflict: 1, matched: 13, not_found: 1 | clarification: 4, conflict: 1, matched: 12, not_found: 1 | clarification: 4, conflict: 1, matched: 12, not_found: 1 |
| `pass_rate` | 1 | 1 | 1 | 1 |
| `status_accuracy` | 1 | 1 | 1 | 1 |
| `auto_coverage` | 0.722 | 0.722 | 0.667 | 0.667 |
| `auto_correct` | 13 | 13 | 12 | 12 |
| `auto_incorrect` | 0 | 0 | 0 | 0 |
| `auto_precision` | 1 | 1 | 1 | 1 |
| `error_upper95` | 0.231 | 0.231 | 0.25 | 0.25 |
| `required_auto_hit` | 1 | 1 | 1 | 1 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 0 |
| `forbidden_code_hits` | 0 | 0 | 0 | 0 |
| `compatible_recall` | 1 | 1 | 1 | 1 |
| `checks_pass` | — | — | — | — |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_resolved` | 1 | 1 | 0.667 | 1 |
| `dialog_cases` | 2 | 2 | 3 | 3 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.5 | 1.5 | 1.5 | 1.33 |
| `latency_ms.p50` | 5.24 | 7.6 | 14.29 | 5.62 |
| `latency_ms.p95` | 15.45 | 14.77 | 29.18 | 10.89 |
| `latency_ms.max` | 16.38 | 19.94 | 32 | 12.77 |
| `latency_ms.mean` | 6.72 | 8.32 | 15.01 | 5.72 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0 | 0 | 0 | 0 |
| `ranking.ranked_cases` | 15 | 15 | 15 | 15 |
| `ranking.hit@1` | 1 | 1 | 1 | 0.933 |
| `ranking.hit@3` | 1 | 1 | 1 | 1 |
| `ranking.hit@5` | 1 | 1 | 1 | 1 |
| `ranking.mrr` | 1 | 1 | 1 | 0.967 |
| `ranking.ndcg@3` | 1 | 1 | 1 | 0.975 |
| `ranking.type_hit@1` | 1 | 1 | 1 | 1 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0 | 0 | 0 | 0 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 1 | 1 | 1 | 0.967 |
| `ranking.dialog_traced` | 15 | 15 | 15 | 15 |
| `ranking.mrr_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 0.967 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.hit1_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 0.933 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.rank_by_step` | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1 → 1 → 1 → 1 → 1 → 1 → 1 | 1.07 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 1 | 1 | 1 | 1 |
| `ranking.questions_to_top1_mean` | 0 | 0 | 0 | 0.07 |
| `ranking.bits_per_question` | 0 | 0 | 0 | 0.25 |
| `ranking.useless_question_rate` | 1 | 1 | 1 | 0.75 |
| `ranking.dead_end_rate` | 0 | 0 | 0 | 0 |

#### synthetic (984 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 984 | 984 | 984 | 984 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 610, conflict: 220, manual_choice: 8, matched: 140, not_found: 6 | clarification: 571, conflict: 240, manual_choice: 8, matched: 159, not_found: 6 | clarification: 614, conflict: 220, manual_choice: 8, matched: 136, not_found: 6 | clarification: 604, conflict: 232, manual_choice: 8, matched: 134, not_found: 6 |
| `pass_rate` | 1 | 1 | 1 | 0.982 |
| `status_accuracy` | 1 | 1 | 1 | 0.982 |
| `auto_coverage` | 0.142 | 0.162 | 0.138 | 0.136 |
| `auto_correct` | 140 | 159 | 136 | 134 |
| `auto_incorrect` | 0 | 0 | 0 | 0 |
| `auto_precision` | 1 | 1 | 1 | 1 |
| `error_upper95` | 0.021 | 0.019 | 0.022 | 0.022 |
| `required_auto_hit` | — | — | — | — |
| `forbidden_auto_violations` | 0 | 0 | 0 | 6 |
| `forbidden_code_hits` | 0 | 0 | 0 | 0 |
| `compatible_recall` | 0.999 | 0.997 | 0.997 | 0.981 |
| `checks_pass` | — | — | — | — |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_resolved` | 0.986 | 0.986 | 0.987 | 0.966 |
| `dialog_cases` | 591 | 572 | 595 | 597 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 2.28 | 2.28 | 2.29 | 2.27 |
| `latency_ms.p50` | 4.68 | 7.07 | 15.78 | 6.16 |
| `latency_ms.p95` | 18.35 | 18.47 | 37.11 | 17.24 |
| `latency_ms.max` | 186.82 | 167.07 | 180.84 | 88.03 |
| `latency_ms.mean` | 6.93 | 8.75 | 17.23 | 7.78 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | — | — | — | — |
| `ranking.ranked_cases` | 731 | 731 | 731 | 731 |
| `ranking.hit@1` | 0.951 | 0.989 | 0.951 | 0.934 |
| `ranking.hit@3` | 0.982 | 0.997 | 0.981 | 0.964 |
| `ranking.hit@5` | 0.99 | 0.997 | 0.989 | 0.973 |
| `ranking.mrr` | 0.968 | 0.992 | 0.967 | 0.951 |
| `ranking.ndcg@3` | 0.965 | 0.989 | 0.964 | 0.942 |
| `ranking.type_hit@1` | 0.997 | 0.997 | 0.997 | 0.981 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.001 | 0.003 | 0.003 | 0.019 |
| `ranking.list_size_median` | 2 | 1 | 2 | 1 |
| `ranking.list_precision_mean` | 0.941 | 0.992 | 0.944 | 0.943 |
| `ranking.dialog_traced` | 731 | 731 | 731 | 731 |
| `ranking.mrr_by_step` | 0.968 → 0.997 → 0.999 → 0.999 → 0.999 → 0.999 → 0.999 | 0.992 → 0.996 → 0.997 → 0.997 → 0.997 → 0.997 → 0.997 | 0.967 → 0.996 → 0.997 → 0.997 → 0.997 → 0.997 → 0.997 | 0.951 → 0.979 → 0.981 → 0.981 → 0.981 → 0.981 → 0.981 |
| `ranking.hit1_by_step` | 0.951 → 0.995 → 0.999 → 0.999 → 0.999 → 0.999 → 0.999 | 0.989 → 0.995 → 0.997 → 0.997 → 0.997 → 0.997 → 0.997 | 0.951 → 0.995 → 0.997 → 0.997 → 0.997 → 0.997 → 0.997 | 0.934 → 0.978 → 0.981 → 0.981 → 0.981 → 0.981 → 0.981 |
| `ranking.rank_by_step` | 1.13 → 1 → 1 → 1 → 1 → 1 → 1 | 1.02 → 1 → 1 → 1 → 1 → 1 → 1 | 1.13 → 1 → 1 → 1 → 1 → 1 → 1 | 1.13 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 0.999 | 0.997 | 0.997 | 0.981 |
| `ranking.questions_to_top1_mean` | 0.05 | 0.01 | 0.05 | 0.05 |
| `ranking.bits_per_question` | 0.458 | 0.391 | 0.452 | 0.451 |
| `ranking.useless_question_rate` | 0.671 | 0.701 | 0.677 | 0.675 |
| `ranking.dead_end_rate` | 0 | 0.001 | 0.001 | 0.001 |

#### edge_inputs (39 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 39 | 39 | 39 | 39 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 2, not_found: 37 | clarification: 2, not_found: 37 | clarification: 2, not_found: 37 | clarification: 2, not_found: 37 |
| `pass_rate` | 1 | 1 | 1 | 1 |
| `status_accuracy` | 1 | 1 | 1 | 1 |
| `auto_coverage` | 0 | 0 | 0 | 0 |
| `auto_correct` | 0 | 0 | 0 | 0 |
| `auto_incorrect` | 0 | 0 | 0 | 0 |
| `auto_precision` | — | — | — | — |
| `error_upper95` | — | — | — | — |
| `required_auto_hit` | — | — | — | — |
| `forbidden_auto_violations` | 0 | 0 | 0 | 0 |
| `forbidden_code_hits` | 0 | 0 | 0 | 0 |
| `compatible_recall` | — | — | — | — |
| `checks_pass` | — | — | — | — |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_resolved` | — | — | — | — |
| `dialog_cases` | 0 | 0 | 0 | 0 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | — | — | — | — |
| `latency_ms.p50` | 0.74 | 0.73 | 1.01 | 0.2 |
| `latency_ms.p95` | 10.53 | 11.89 | 13.84 | 7.37 |
| `latency_ms.max` | 570.78 | 562.28 | 486.55 | 400.42 |
| `latency_ms.mean` | 25.68 | 25.53 | 25.86 | 21.3 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | — | — | — | — |
| `ranking.ranked_cases` | 0 | 0 | 0 | 0 |
| `ranking.dialog_traced` | 0 | 0 | 0 | 0 |

#### glued_words (100 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 100 | 100 | 100 | 100 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 45, conflict: 1, manual_choice: 2, matched: 26, not_found: 26 | clarification: 44, conflict: 1, manual_choice: 1, matched: 12, not_found: 42 | clarification: 47, manual_choice: 1, matched: 10, not_found: 42 | clarification: 46, conflict: 1, manual_choice: 1, matched: 10, not_found: 42 |
| `pass_rate` | 0.45 | 0.26 | 0.24 | 0.22 |
| `status_accuracy` | 0.48 | 0.3 | 0.28 | 0.28 |
| `auto_coverage` | 0.26 | 0.12 | 0.1 | 0.1 |
| `auto_correct` | 25 | 11 | 8 | 7 |
| `auto_incorrect` | 1 | 1 | 2 | 3 |
| `auto_precision` | 0.962 | 0.917 | 0.8 | 0.7 |
| `error_upper95` | — | — | — | — |
| `required_auto_hit` | 0.391 | 0.172 | 0.125 | 0.109 |
| `forbidden_auto_violations` | 0 | 1 | 1 | 1 |
| `forbidden_code_hits` | 1 | 0 | 1 | 1 |
| `compatible_recall` | 0.71 | 0.47 | 0.5 | 0.48 |
| `checks_pass` | 0.59 | 0.35 | 0.39 | 0.36 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 59 / 100 | 35 / 100 | 39 / 100 | 36 / 100 |
| `dialog_resolved` | 0.527 | 0.307 | 0.367 | 0.356 |
| `dialog_cases` | 74 | 88 | 90 | 90 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 2.21 | 2.26 | 2.39 | 2.41 |
| `latency_ms.p50` | 12.06 | 11.63 | 19.47 | 11.17 |
| `latency_ms.p95` | 217.49 | 235.36 | 299.08 | 233.95 |
| `latency_ms.max` | 676.26 | 661.81 | 945.04 | 812.1 |
| `latency_ms.mean` | 34.03 | 42.27 | 64.65 | 44.08 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.594 | 0.828 | 0.859 | 0.859 |
| `ranking.ranked_cases` | 100 | 100 | 100 | 100 |
| `ranking.hit@1` | 0.58 | 0.32 | 0.32 | 0.3 |
| `ranking.hit@3` | 0.66 | 0.41 | 0.42 | 0.4 |
| `ranking.hit@5` | 0.69 | 0.45 | 0.46 | 0.44 |
| `ranking.mrr` | 0.628 | 0.376 | 0.382 | 0.362 |
| `ranking.ndcg@3` | 0.623 | 0.372 | 0.378 | 0.358 |
| `ranking.type_hit@1` | 0.69 | 0.43 | 0.45 | 0.43 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.29 | 0.53 | 0.5 | 0.52 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.683 | 0.474 | 0.434 | 0.423 |
| `ranking.dialog_traced` | 100 | 100 | 100 | 100 |
| `ranking.mrr_by_step` | 0.628 → 0.68 → 0.703 → 0.703 → 0.703 → 0.703 → 0.703 | 0.376 → 0.431 → 0.446 → 0.446 → 0.446 → 0.446 → 0.446 | 0.382 → 0.453 → 0.486 → 0.486 → 0.486 → 0.486 → 0.486 | 0.362 → 0.433 → 0.466 → 0.466 → 0.466 → 0.466 → 0.466 |
| `ranking.hit1_by_step` | 0.58 → 0.66 → 0.7 → 0.7 → 0.7 → 0.7 → 0.7 | 0.32 → 0.4 → 0.43 → 0.43 → 0.43 → 0.43 → 0.43 | 0.32 → 0.42 → 0.48 → 0.48 → 0.48 → 0.48 → 0.48 | 0.3 → 0.4 → 0.46 → 0.46 → 0.46 → 0.46 → 0.46 |
| `ranking.rank_by_step` | 2.08 → 1.13 → 1.03 → 1.03 → 1.03 → 1.03 → 1.03 | 1.79 → 1.21 → 1.15 → 1.15 → 1.15 → 1.15 → 1.15 | 3 → 1.28 → 1.1 → 1.1 → 1.1 → 1.1 → 1.1 | 3.08 → 1.29 → 1.1 → 1.1 → 1.1 → 1.1 → 1.1 |
| `ranking.top1_reached` | 0.7 | 0.43 | 0.48 | 0.46 |
| `ranking.questions_to_top1_mean` | 0.23 | 0.33 | 0.46 | 0.48 |
| `ranking.bits_per_question` | 0.638 | 0.626 | 0.744 | 0.726 |
| `ranking.useless_question_rate` | 0.562 | 0.651 | 0.559 | 0.56 |
| `ranking.dead_end_rate` | 0.02 | 0.09 | 0.06 | 0.06 |

#### injection (105 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 105 | 105 | 105 | 105 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 55, conflict: 1, manual_choice: 6, matched: 43 | clarification: 48, conflict: 5, manual_choice: 5, matched: 47 | clarification: 61, conflict: 3, manual_choice: 5, matched: 36 | clarification: 63, conflict: 4, manual_choice: 4, matched: 34 |
| `pass_rate` | 0.638 | 0.695 | 0.571 | 0.552 |
| `status_accuracy` | 0.686 | 0.705 | 0.61 | 0.59 |
| `auto_coverage` | 0.41 | 0.448 | 0.343 | 0.324 |
| `auto_correct` | 40 | 47 | 33 | 32 |
| `auto_incorrect` | 3 | 0 | 3 | 2 |
| `auto_precision` | 0.93 | 1 | 0.917 | 0.941 |
| `error_upper95` | — | 0.064 | — | — |
| `required_auto_hit` | 0.526 | 0.618 | 0.434 | 0.421 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 0 |
| `forbidden_code_hits` | 3 | 0 | 3 | 2 |
| `compatible_recall` | 0.962 | 0.952 | 0.943 | 0.933 |
| `checks_pass` | 0.914 | 0.895 | 0.924 | 0.924 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 96 / 105 | 94 / 105 | 97 / 105 | 97 / 105 |
| `dialog_resolved` | 0.952 | 0.879 | 0.87 | 0.845 |
| `dialog_cases` | 62 | 58 | 69 | 71 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.86 | 1.69 | 1.85 | 1.82 |
| `latency_ms.p50` | 10.49 | 17.52 | 25.06 | 14.47 |
| `latency_ms.p95` | 36.62 | 37.11 | 54.68 | 32.35 |
| `latency_ms.max` | 77.99 | 95.28 | 101.37 | 104.08 |
| `latency_ms.mean` | 14.3 | 20.69 | 28.72 | 17.62 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.434 | 0.382 | 0.526 | 0.553 |
| `ranking.ranked_cases` | 105 | 105 | 105 | 105 |
| `ranking.hit@1` | 0.743 | 0.867 | 0.705 | 0.714 |
| `ranking.hit@3` | 0.914 | 0.914 | 0.876 | 0.867 |
| `ranking.hit@5` | 0.924 | 0.933 | 0.895 | 0.886 |
| `ranking.mrr` | 0.829 | 0.897 | 0.795 | 0.797 |
| `ranking.ndcg@3` | 0.845 | 0.897 | 0.808 | 0.807 |
| `ranking.type_hit@1` | 0.99 | 0.952 | 0.971 | 0.962 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.038 | 0.048 | 0.057 | 0.067 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.765 | 0.927 | 0.748 | 0.762 |
| `ranking.dialog_traced` | 105 | 105 | 105 | 105 |
| `ranking.mrr_by_step` | 0.829 → 0.935 → 0.962 → 0.962 → 0.962 → 0.962 → 0.962 | 0.897 → 0.935 → 0.946 → 0.946 → 0.946 → 0.946 → 0.946 | 0.795 → 0.902 → 0.93 → 0.93 → 0.93 → 0.93 → 0.93 | 0.797 → 0.89 → 0.918 → 0.918 → 0.918 → 0.918 → 0.918 |
| `ranking.hit1_by_step` | 0.743 → 0.914 → 0.962 → 0.962 → 0.962 → 0.962 → 0.962 | 0.867 → 0.924 → 0.943 → 0.943 → 0.943 → 0.943 → 0.943 | 0.705 → 0.876 → 0.924 → 0.924 → 0.924 → 0.924 → 0.924 | 0.714 → 0.867 → 0.914 → 0.914 → 0.914 → 0.914 → 0.914 |
| `ranking.rank_by_step` | 1.94 → 1.08 → 1 → 1 → 1 → 1 → 1 | 1.29 → 1.05 → 1.02 → 1.02 → 1.02 → 1.02 → 1.02 | 2.06 → 1.13 → 1.04 → 1.04 → 1.04 → 1.04 → 1.04 | 2.04 → 1.21 → 1.12 → 1.12 → 1.12 → 1.12 → 1.12 |
| `ranking.top1_reached` | 0.962 | 0.943 | 0.924 | 0.914 |
| `ranking.questions_to_top1_mean` | 0.28 | 0.1 | 0.29 | 0.27 |
| `ranking.bits_per_question` | 0.58 | 0.319 | 0.492 | 0.465 |
| `ranking.useless_question_rate` | 0.598 | 0.765 | 0.667 | 0.671 |
| `ranking.dead_end_rate` | 0 | 0 | 0 | 0.01 |

#### invariance (480 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 480 | 480 | 480 | 480 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 244, conflict: 13, manual_choice: 14, matched: 209 | clarification: 211, conflict: 17, manual_choice: 10, matched: 222, not_found: 20 | clarification: 268, conflict: 5, manual_choice: 10, matched: 177, not_found: 20 | clarification: 265, conflict: 5, manual_choice: 10, matched: 180, not_found: 20 |
| `pass_rate` | 0.725 | 0.746 | 0.648 | 0.646 |
| `status_accuracy` | 0.735 | 0.746 | 0.658 | 0.658 |
| `auto_coverage` | 0.435 | 0.463 | 0.369 | 0.375 |
| `auto_correct` | 204 | 222 | 172 | 175 |
| `auto_incorrect` | 5 | 0 | 5 | 5 |
| `auto_precision` | 0.976 | 1 | 0.972 | 0.972 |
| `error_upper95` | — | 0.014 | — | — |
| `required_auto_hit` | 0.613 | 0.664 | 0.517 | 0.52 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 1 |
| `forbidden_code_hits` | 5 | 0 | 5 | 5 |
| `compatible_recall` | 0.981 | 0.919 | 0.929 | 0.927 |
| `checks_pass` | 0.971 | 0.931 | 0.929 | 0.927 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 466 / 480 | 447 / 480 | 446 / 480 | 445 / 480 |
| `dialog_resolved` | 0.945 | 0.752 | 0.785 | 0.813 |
| `dialog_cases` | 271 | 258 | 303 | 300 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.8 | 1.6 | 1.89 | 1.85 |
| `latency_ms.p50` | 8.98 | 13.98 | 21.49 | 10.71 |
| `latency_ms.p95` | 23.4 | 33.53 | 46.68 | 25.29 |
| `latency_ms.max` | 89.99 | 403.38 | 230.65 | 163.47 |
| `latency_ms.mean` | 11.46 | 17.23 | 24.74 | 12.89 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.372 | 0.336 | 0.468 | 0.465 |
| `ranking.ranked_cases` | 480 | 480 | 480 | 480 |
| `ranking.hit@1` | 0.881 | 0.867 | 0.8 | 0.81 |
| `ranking.hit@3` | 0.952 | 0.89 | 0.885 | 0.885 |
| `ranking.hit@5` | 0.967 | 0.912 | 0.91 | 0.908 |
| `ranking.mrr` | 0.918 | 0.884 | 0.848 | 0.852 |
| `ranking.ndcg@3` | 0.921 | 0.88 | 0.849 | 0.852 |
| `ranking.type_hit@1` | 0.996 | 0.919 | 0.944 | 0.944 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.019 | 0.081 | 0.071 | 0.073 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.874 | 0.936 | 0.83 | 0.847 |
| `ranking.dialog_traced` | 480 | 480 | 480 | 480 |
| `ranking.mrr_by_step` | 0.918 → 0.975 → 0.982 → 0.984 → 0.984 → 0.984 → 0.984 | 0.884 → 0.903 → 0.916 → 0.916 → 0.916 → 0.916 → 0.916 | 0.848 → 0.911 → 0.926 → 0.927 → 0.927 → 0.927 → 0.927 | 0.852 → 0.909 → 0.922 → 0.924 → 0.924 → 0.924 → 0.924 |
| `ranking.hit1_by_step` | 0.881 → 0.967 → 0.979 → 0.983 → 0.983 → 0.983 → 0.983 | 0.867 → 0.896 → 0.915 → 0.915 → 0.915 → 0.915 → 0.915 | 0.8 → 0.9 → 0.923 → 0.925 → 0.925 → 0.925 → 0.925 | 0.81 → 0.898 → 0.919 → 0.923 → 0.923 → 0.923 → 0.923 |
| `ranking.rank_by_step` | 1.31 → 1.03 → 1.01 → 1 → 1 → 1 → 1 | 1.18 → 1.08 → 1.01 → 1.01 → 1.01 → 1.01 → 1.01 | 1.41 → 1.07 → 1.01 → 1 → 1 → 1 → 1 | 1.4 → 1.12 → 1.06 → 1.05 → 1.05 → 1.05 → 1.05 |
| `ranking.top1_reached` | 0.983 | 0.915 | 0.925 | 0.923 |
| `ranking.questions_to_top1_mean` | 0.12 | 0.07 | 0.16 | 0.15 |
| `ranking.bits_per_question` | 0.477 | 0.419 | 0.442 | 0.432 |
| `ranking.useless_question_rate` | 0.68 | 0.748 | 0.721 | 0.711 |
| `ranking.dead_end_rate` | 0.004 | 0.004 | 0.008 | 0.008 |

#### lazy_numbers (1173 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 1173 | 1173 | 1173 | 1173 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 689, conflict: 126, manual_choice: 41, matched: 303, not_found: 14 | clarification: 806, conflict: 43, manual_choice: 49, matched: 261, not_found: 14 | clarification: 806, conflict: 39, manual_choice: 49, matched: 265, not_found: 14 | clarification: 833, conflict: 54, manual_choice: 49, matched: 223, not_found: 14 |
| `pass_rate` | 0.714 | 0.723 | 0.727 | 0.713 |
| `status_accuracy` | 0.805 | 0.768 | 0.77 | 0.749 |
| `auto_coverage` | 0.258 | 0.223 | 0.226 | 0.19 |
| `auto_correct` | 245 | 201 | 204 | 171 |
| `auto_incorrect` | 58 | 60 | 61 | 52 |
| `auto_precision` | 0.809 | 0.77 | 0.77 | 0.767 |
| `error_upper95` | — | — | — | — |
| `required_auto_hit` | 0.644 | 0.528 | 0.536 | 0.449 |
| `forbidden_auto_violations` | 58 | 60 | 61 | 52 |
| `forbidden_code_hits` | 58 | 60 | 61 | 52 |
| `compatible_recall` | 0.976 | 0.956 | 0.96 | 0.95 |
| `checks_pass` | 0.702 | 0.756 | 0.76 | 0.749 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 302 / 430 | 325 / 430 | 327 / 430 | 322 / 430 |
| `dialog_resolved` | 0.895 | 0.729 | 0.699 | 0.719 |
| `dialog_cases` | 697 | 741 | 738 | 771 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 2.22 | 2.19 | 2.18 | 2.14 |
| `latency_ms.p50` | 7.32 | 10.24 | 19 | 7.96 |
| `latency_ms.p95` | 13.45 | 16.73 | 33.61 | 13.5 |
| `latency_ms.max` | 238.09 | 35.11 | 213.57 | 88.54 |
| `latency_ms.mean` | 8.38 | 10.75 | 20.16 | 8.34 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.354 | 0.47 | 0.462 | 0.549 |
| `ranking.ranked_cases` | 944 | 944 | 944 | 944 |
| `ranking.hit@1` | 0.952 | 0.931 | 0.906 | 0.926 |
| `ranking.hit@3` | 0.974 | 0.952 | 0.957 | 0.947 |
| `ranking.hit@5` | 0.976 | 0.954 | 0.959 | 0.949 |
| `ranking.mrr` | 0.963 | 0.942 | 0.931 | 0.936 |
| `ranking.ndcg@3` | 0.963 | 0.942 | 0.935 | 0.937 |
| `ranking.type_hit@1` | 0.98 | 0.96 | 0.964 | 0.954 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.024 | 0.044 | 0.04 | 0.05 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.959 | 0.969 | 0.953 | 0.968 |
| `ranking.dialog_traced` | 944 | 944 | 944 | 944 |
| `ranking.mrr_by_step` | 0.963 → 0.972 → 0.974 → 0.976 → 0.976 → 0.976 → 0.976 | 0.942 → 0.951 → 0.955 → 0.956 → 0.956 → 0.956 → 0.956 | 0.931 → 0.954 → 0.959 → 0.96 → 0.96 → 0.96 → 0.96 | 0.936 → 0.946 → 0.95 → 0.95 → 0.95 → 0.95 → 0.95 |
| `ranking.hit1_by_step` | 0.952 → 0.968 → 0.972 → 0.976 → 0.976 → 0.976 → 0.976 | 0.931 → 0.948 → 0.954 → 0.956 → 0.956 → 0.956 → 0.956 | 0.906 → 0.949 → 0.959 → 0.96 → 0.96 → 0.96 → 0.96 | 0.926 → 0.943 → 0.949 → 0.95 → 0.95 → 0.95 → 0.95 |
| `ranking.rank_by_step` | 1.03 → 1.01 → 1 → 1 → 1 → 1 → 1 | 1.09 → 1.02 → 1 → 1 → 1 → 1 → 1 | 1.12 → 1.02 → 1 → 1 → 1 → 1 → 1 | 1.09 → 1.02 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 0.976 | 0.956 | 0.96 | 0.95 |
| `ranking.questions_to_top1_mean` | 0.03 | 0.03 | 0.07 | 0.03 |
| `ranking.bits_per_question` | 0.114 | 0.131 | 0.144 | 0.131 |
| `ranking.useless_question_rate` | 0.908 | 0.9 | 0.886 | 0.901 |
| `ranking.dead_end_rate` | 0.005 | 0.004 | 0.004 | 0.004 |

#### lazy_user (236 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 236 | 236 | 236 | 236 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 132, conflict: 2, manual_choice: 9, matched: 92, not_found: 1 | clarification: 151, conflict: 7, manual_choice: 9, matched: 68, not_found: 1 | clarification: 160, conflict: 3, manual_choice: 9, matched: 63, not_found: 1 | clarification: 159, conflict: 5, manual_choice: 9, matched: 62, not_found: 1 |
| `pass_rate` | 0.78 | 0.716 | 0.678 | 0.64 |
| `status_accuracy` | 0.814 | 0.72 | 0.708 | 0.686 |
| `auto_coverage` | 0.39 | 0.288 | 0.267 | 0.263 |
| `auto_correct` | 89 | 68 | 60 | 59 |
| `auto_incorrect` | 3 | 0 | 3 | 3 |
| `auto_precision` | 0.967 | 1 | 0.952 | 0.952 |
| `error_upper95` | — | 0.044 | — | — |
| `required_auto_hit` | 0.586 | 0.423 | 0.36 | 0.351 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 1 |
| `forbidden_code_hits` | 3 | 0 | 3 | 3 |
| `compatible_recall` | 0.958 | 0.966 | 0.953 | 0.941 |
| `checks_pass` | 0.903 | 0.778 | 0.824 | 0.778 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 159 / 176 | 137 / 176 | 145 / 176 | 137 / 176 |
| `dialog_resolved` | 0.889 | 0.839 | 0.786 | 0.81 |
| `dialog_cases` | 144 | 168 | 173 | 174 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.81 | 1.8 | 1.82 | 1.85 |
| `latency_ms.p50` | 7.34 | 12.63 | 19.51 | 8.93 |
| `latency_ms.p95` | 19.64 | 27.9 | 44.45 | 19.99 |
| `latency_ms.max` | 60.27 | 229.09 | 285.02 | 60.29 |
| `latency_ms.mean` | 9.45 | 15.37 | 23.56 | 10.54 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.387 | 0.577 | 0.613 | 0.631 |
| `ranking.ranked_cases` | 236 | 236 | 236 | 236 |
| `ranking.hit@1` | 0.894 | 0.886 | 0.869 | 0.873 |
| `ranking.hit@3` | 0.936 | 0.919 | 0.915 | 0.911 |
| `ranking.hit@5` | 0.953 | 0.962 | 0.949 | 0.936 |
| `ranking.mrr` | 0.919 | 0.912 | 0.899 | 0.898 |
| `ranking.ndcg@3` | 0.916 | 0.902 | 0.892 | 0.89 |
| `ranking.type_hit@1` | 0.992 | 0.966 | 0.983 | 0.975 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.042 | 0.034 | 0.047 | 0.059 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.887 | 0.912 | 0.857 | 0.879 |
| `ranking.dialog_traced` | 236 | 236 | 236 | 236 |
| `ranking.mrr_by_step` | 0.919 → 0.956 → 0.964 → 0.964 → 0.964 → 0.964 → 0.964 | 0.912 → 0.943 → 0.957 → 0.966 → 0.966 → 0.966 → 0.966 | 0.899 → 0.943 → 0.953 → 0.953 → 0.953 → 0.953 → 0.953 | 0.898 → 0.93 → 0.941 → 0.941 → 0.941 → 0.941 → 0.941 |
| `ranking.hit1_by_step` | 0.894 → 0.945 → 0.962 → 0.962 → 0.962 → 0.962 → 0.962 | 0.886 → 0.928 → 0.953 → 0.966 → 0.966 → 0.966 → 0.966 | 0.869 → 0.932 → 0.953 → 0.953 → 0.953 → 0.953 → 0.953 | 0.873 → 0.919 → 0.941 → 0.941 → 0.941 → 0.941 → 0.941 |
| `ranking.rank_by_step` | 1.14 → 1.02 → 1 → 1 → 1 → 1 → 1 | 1.21 → 1.08 → 1.04 → 1 → 1 → 1 → 1 | 1.2 → 1.02 → 1 → 1 → 1 → 1 → 1 | 1.16 → 1.02 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 0.962 | 0.966 | 0.953 | 0.941 |
| `ranking.questions_to_top1_mean` | 0.09 | 0.14 | 0.11 | 0.09 |
| `ranking.bits_per_question` | 0.311 | 0.364 | 0.312 | 0.303 |
| `ranking.useless_question_rate` | 0.768 | 0.751 | 0.781 | 0.783 |
| `ranking.dead_end_rate` | 0.017 | 0 | 0.017 | 0.021 |

#### monotonicity (120 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 120 | 120 | 120 | 120 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 36, conflict: 6, manual_choice: 4, matched: 74 | clarification: 26, conflict: 2, manual_choice: 4, matched: 88 | clarification: 46, conflict: 1, manual_choice: 4, matched: 69 | clarification: 51, conflict: 1, manual_choice: 4, matched: 64 |
| `pass_rate` | 0.608 | 0.75 | 0.567 | 0.525 |
| `status_accuracy` | 0.642 | 0.758 | 0.6 | 0.558 |
| `auto_coverage` | 0.617 | 0.733 | 0.575 | 0.533 |
| `auto_correct` | 70 | 87 | 65 | 60 |
| `auto_incorrect` | 4 | 1 | 4 | 4 |
| `auto_precision` | 0.946 | 0.989 | 0.942 | 0.938 |
| `error_upper95` | — | — | — | — |
| `required_auto_hit` | 0.598 | 0.744 | 0.556 | 0.513 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 0 |
| `forbidden_code_hits` | 4 | 1 | 4 | 4 |
| `compatible_recall` | 0.958 | 0.975 | 0.958 | 0.958 |
| `checks_pass` | 0.992 | 1 | 1 | 1 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.subset_of` | 119 / 120 | 120 / 120 | 120 / 120 | 120 / 120 |
| `dialog_resolved` | 0.891 | 0.75 | 0.843 | 0.821 |
| `dialog_cases` | 46 | 32 | 51 | 56 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.71 | 1.25 | 1.81 | 1.72 |
| `latency_ms.p50` | 7.46 | 11.35 | 18.49 | 10.24 |
| `latency_ms.p95` | 33.19 | 41.6 | 45.25 | 39.61 |
| `latency_ms.max` | 43.96 | 51.46 | 56.38 | 50.51 |
| `latency_ms.mean` | 10.17 | 14.06 | 21.59 | 12.6 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.368 | 0.248 | 0.41 | 0.453 |
| `ranking.ranked_cases` | 120 | 120 | 120 | 120 |
| `ranking.hit@1` | 0.842 | 0.917 | 0.8 | 0.8 |
| `ranking.hit@3` | 0.942 | 0.967 | 0.933 | 0.933 |
| `ranking.hit@5` | 0.958 | 0.975 | 0.958 | 0.958 |
| `ranking.mrr` | 0.891 | 0.943 | 0.868 | 0.868 |
| `ranking.ndcg@3` | 0.901 | 0.948 | 0.881 | 0.881 |
| `ranking.type_hit@1` | 0.992 | 0.983 | 0.992 | 0.992 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.042 | 0.025 | 0.042 | 0.042 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.843 | 0.938 | 0.807 | 0.809 |
| `ranking.dialog_traced` | 120 | 120 | 120 | 120 |
| `ranking.mrr_by_step` | 0.891 → 0.958 → 0.963 → 0.967 → 0.967 → 0.967 → 0.967 | 0.943 → 0.975 → 0.975 → 0.975 → 0.975 → 0.975 → 0.975 | 0.868 → 0.949 → 0.958 → 0.958 → 0.958 → 0.958 → 0.958 | 0.868 → 0.949 → 0.958 → 0.958 → 0.958 → 0.958 → 0.958 |
| `ranking.hit1_by_step` | 0.842 → 0.95 → 0.958 → 0.967 → 0.967 → 0.967 → 0.967 | 0.917 → 0.975 → 0.975 → 0.975 → 0.975 → 0.975 → 0.975 | 0.8 → 0.942 → 0.958 → 0.958 → 0.958 → 0.958 → 0.958 | 0.8 → 0.942 → 0.958 → 0.958 → 0.958 → 0.958 → 0.958 |
| `ranking.rank_by_step` | 1.19 → 1.02 → 1.01 → 1 → 1 → 1 → 1 | 1.09 → 1 → 1 → 1 → 1 → 1 → 1 | 1.26 → 1.03 → 1 → 1 → 1 → 1 → 1 | 1.26 → 1.03 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 0.967 | 0.975 | 0.958 | 0.958 |
| `ranking.questions_to_top1_mean` | 0.16 | 0.06 | 0.18 | 0.18 |
| `ranking.bits_per_question` | 0.396 | 0.263 | 0.388 | 0.35 |
| `ranking.useless_question_rate` | 0.656 | 0.818 | 0.692 | 0.729 |
| `ranking.dead_end_rate` | 0 | 0 | 0 | 0 |

#### multi_item (60 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 60 | 60 | 60 | 60 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 24, conflict: 7, manual_choice: 3, matched: 26 | clarification: 34, conflict: 8, manual_choice: 3, matched: 15 | clarification: 24, conflict: 3, manual_choice: 3, matched: 30 | clarification: 21, conflict: 5, manual_choice: 3, matched: 31 |
| `pass_rate` | 0.567 | 0.75 | 0.5 | 0.483 |
| `status_accuracy` | 0.567 | 0.75 | 0.5 | 0.483 |
| `auto_coverage` | 0.433 | 0.25 | 0.5 | 0.517 |
| `auto_correct` | 0 | 0 | 0 | 0 |
| `auto_incorrect` | 26 | 15 | 30 | 31 |
| `auto_precision` | 0 | 0 | 0 | 0 |
| `error_upper95` | — | — | — | — |
| `required_auto_hit` | — | — | — | — |
| `forbidden_auto_violations` | 26 | 15 | 30 | 31 |
| `forbidden_code_hits` | 25 | 14 | 29 | 29 |
| `compatible_recall` | — | — | — | — |
| `checks_pass` | — | — | — | — |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_resolved` | — | — | — | — |
| `dialog_cases` | 0 | 0 | 0 | 0 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | — | — | — | — |
| `latency_ms.p50` | 15.95 | 23.82 | 33.49 | 22.06 |
| `latency_ms.p95` | 81.89 | 83.48 | 86.58 | 81.61 |
| `latency_ms.max` | 196.66 | 203.24 | 220.84 | 199.08 |
| `latency_ms.mean` | 25.17 | 31.81 | 41.42 | 29.29 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | — | — | — | — |
| `ranking.ranked_cases` | 0 | 0 | 0 | 0 |
| `ranking.dialog_traced` | 0 | 0 | 0 | 0 |

#### number_errors (160 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 160 | 160 | 160 | 160 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 100, conflict: 27, manual_choice: 3, matched: 30 | clarification: 92, conflict: 25, manual_choice: 6, matched: 37 | clarification: 110, conflict: 21, manual_choice: 6, matched: 23 | clarification: 107, conflict: 22, manual_choice: 5, matched: 26 |
| `pass_rate` | 0.656 | 0.613 | 0.681 | 0.669 |
| `status_accuracy` | 0.812 | 0.769 | 0.856 | 0.838 |
| `auto_coverage` | 0.188 | 0.231 | 0.144 | 0.163 |
| `auto_correct` | 29 | 37 | 22 | 25 |
| `auto_incorrect` | 1 | 0 | 1 | 1 |
| `auto_precision` | 0.967 | 1 | 0.957 | 0.962 |
| `error_upper95` | — | 0.081 | — | — |
| `required_auto_hit` | — | — | — | — |
| `forbidden_auto_violations` | 30 | 37 | 23 | 26 |
| `forbidden_code_hits` | 1 | 0 | 1 | 1 |
| `compatible_recall` | 0.869 | 0.844 | 0.856 | 0.844 |
| `checks_pass` | 0.681 | 0.637 | 0.681 | 0.681 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.no_feature` | 109 / 160 | 102 / 160 | 109 / 160 | 109 / 160 |
| `dialog_resolved` | 0.762 | 0.626 | 0.642 | 0.657 |
| `dialog_cases` | 130 | 123 | 137 | 134 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.86 | 1.77 | 1.89 | 1.76 |
| `latency_ms.p50` | 9.67 | 12.52 | 21.57 | 10.95 |
| `latency_ms.p95` | 22.96 | 24.06 | 42.5 | 19.91 |
| `latency_ms.max` | 262.09 | 211.72 | 57.3 | 40.39 |
| `latency_ms.mean` | 12.6 | 14.72 | 22.82 | 11.34 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | — | — | — | — |
| `ranking.ranked_cases` | 160 | 160 | 160 | 160 |
| `ranking.hit@1` | 0.738 | 0.762 | 0.694 | 0.706 |
| `ranking.hit@3` | 0.844 | 0.806 | 0.819 | 0.806 |
| `ranking.hit@5` | 0.85 | 0.819 | 0.825 | 0.812 |
| `ranking.mrr` | 0.79 | 0.787 | 0.756 | 0.758 |
| `ranking.ndcg@3` | 0.796 | 0.785 | 0.763 | 0.761 |
| `ranking.type_hit@1` | 0.887 | 0.844 | 0.869 | 0.863 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.131 | 0.156 | 0.144 | 0.156 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.81 | 0.888 | 0.772 | 0.797 |
| `ranking.dialog_traced` | 160 | 160 | 160 | 160 |
| `ranking.mrr_by_step` | 0.79 → 0.844 → 0.863 → 0.866 → 0.866 → 0.866 → 0.866 | 0.787 → 0.811 → 0.819 → 0.829 → 0.829 → 0.829 → 0.829 | 0.756 → 0.806 → 0.824 → 0.829 → 0.829 → 0.829 → 0.829 | 0.758 → 0.805 → 0.82 → 0.825 → 0.825 → 0.825 → 0.825 |
| `ranking.hit1_by_step` | 0.738 → 0.825 → 0.856 → 0.863 → 0.863 → 0.863 → 0.863 | 0.762 → 0.8 → 0.812 → 0.825 → 0.825 → 0.825 → 0.825 | 0.694 → 0.781 → 0.812 → 0.819 → 0.819 → 0.819 → 0.819 | 0.706 → 0.787 → 0.812 → 0.819 → 0.819 → 0.819 → 0.819 |
| `ranking.rank_by_step` | 1.29 → 1.12 → 1.06 → 1.05 → 1.05 → 1.05 → 1.05 | 1.45 → 1.35 → 1.14 → 1.09 → 1.09 → 1.09 → 1.09 | 1.58 → 1.39 → 1.16 → 1.13 → 1.13 → 1.13 → 1.13 | 1.54 → 1.36 → 1.13 → 1.1 → 1.1 → 1.1 → 1.1 |
| `ranking.top1_reached` | 0.863 | 0.825 | 0.819 | 0.819 |
| `ranking.questions_to_top1_mean` | 0.2 | 0.12 | 0.21 | 0.18 |
| `ranking.bits_per_question` | 0.349 | 0.297 | 0.314 | 0.328 |
| `ranking.useless_question_rate` | 0.778 | 0.815 | 0.801 | 0.799 |
| `ranking.dead_end_rate` | 0.075 | 0.062 | 0.062 | 0.069 |

#### procurement_noise (105 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 105 | 105 | 105 | 105 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 55, conflict: 2, manual_choice: 6, matched: 40, not_found: 2 | clarification: 50, conflict: 3, manual_choice: 5, matched: 47 | clarification: 59, conflict: 2, manual_choice: 5, matched: 39 | clarification: 56, conflict: 2, manual_choice: 5, matched: 42 |
| `pass_rate` | 0.724 | 0.81 | 0.724 | 0.733 |
| `status_accuracy` | 0.743 | 0.81 | 0.743 | 0.762 |
| `auto_coverage` | 0.381 | 0.448 | 0.371 | 0.4 |
| `auto_correct` | 38 | 47 | 37 | 39 |
| `auto_incorrect` | 2 | 0 | 2 | 3 |
| `auto_precision` | 0.95 | 1 | 0.949 | 0.929 |
| `error_upper95` | — | 0.064 | — | — |
| `required_auto_hit` | 0.594 | 0.719 | 0.578 | 0.594 |
| `forbidden_auto_violations` | 0 | 0 | 0 | 0 |
| `forbidden_code_hits` | 2 | 0 | 2 | 3 |
| `compatible_recall` | 0.943 | 0.962 | 0.952 | 0.943 |
| `checks_pass` | 0.914 | 0.981 | 0.952 | 0.952 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 96 / 105 | 103 / 105 | 100 / 105 | 100 / 105 |
| `dialog_resolved` | 0.8 | 0.897 | 0.864 | 0.873 |
| `dialog_cases` | 65 | 58 | 66 | 63 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.96 | 1.65 | 1.95 | 1.95 |
| `latency_ms.p50` | 10.53 | 13.55 | 19.66 | 11.38 |
| `latency_ms.p95` | 40.81 | 33.21 | 48.58 | 29.57 |
| `latency_ms.max` | 57.04 | 57.53 | 80.72 | 53.87 |
| `latency_ms.mean` | 13.79 | 15.32 | 23.42 | 13.13 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.375 | 0.281 | 0.391 | 0.359 |
| `ranking.ranked_cases` | 105 | 105 | 105 | 105 |
| `ranking.hit@1` | 0.876 | 0.924 | 0.848 | 0.876 |
| `ranking.hit@3` | 0.914 | 0.943 | 0.905 | 0.905 |
| `ranking.hit@5` | 0.924 | 0.962 | 0.933 | 0.924 |
| `ranking.mrr` | 0.899 | 0.938 | 0.885 | 0.897 |
| `ranking.ndcg@3` | 0.891 | 0.926 | 0.873 | 0.884 |
| `ranking.type_hit@1` | 0.971 | 0.971 | 0.981 | 0.981 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.057 | 0.038 | 0.048 | 0.057 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.82 | 0.924 | 0.8 | 0.82 |
| `ranking.dialog_traced` | 105 | 105 | 105 | 105 |
| `ranking.mrr_by_step` | 0.899 → 0.921 → 0.933 → 0.933 → 0.933 → 0.933 → 0.933 | 0.938 → 0.957 → 0.962 → 0.962 → 0.962 → 0.962 → 0.962 | 0.885 → 0.935 → 0.952 → 0.952 → 0.952 → 0.952 → 0.952 | 0.897 → 0.926 → 0.943 → 0.943 → 0.943 → 0.943 → 0.943 |
| `ranking.hit1_by_step` | 0.876 → 0.905 → 0.924 → 0.924 → 0.924 → 0.924 → 0.924 | 0.924 → 0.952 → 0.962 → 0.962 → 0.962 → 0.962 → 0.962 | 0.848 → 0.924 → 0.952 → 0.952 → 0.952 → 0.952 → 0.952 | 0.876 → 0.914 → 0.943 → 0.943 → 0.943 → 0.943 → 0.943 |
| `ranking.rank_by_step` | 1.63 → 1.07 → 1.02 → 1.02 → 1.02 → 1.02 → 1.02 | 1.08 → 1.01 → 1 → 1 → 1 → 1 → 1 | 1.7 → 1.06 → 1 → 1 → 1 → 1 → 1 | 1.65 → 1.06 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 0.924 | 0.962 | 0.952 | 0.943 |
| `ranking.questions_to_top1_mean` | 0.07 | 0.05 | 0.14 | 0.1 |
| `ranking.bits_per_question` | 0.452 | 0.515 | 0.57 | 0.546 |
| `ranking.useless_question_rate` | 0.651 | 0.606 | 0.594 | 0.591 |
| `ranking.dead_end_rate` | 0.019 | 0.01 | 0.01 | 0.01 |

#### typos_human (202 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 202 | 202 | 202 | 202 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 77, conflict: 2, manual_choice: 5, matched: 67, not_found: 51 | clarification: 77, conflict: 1, manual_choice: 4, matched: 67, not_found: 53 | clarification: 88, conflict: 1, manual_choice: 4, matched: 56, not_found: 53 | clarification: 85, conflict: 1, manual_choice: 4, matched: 59, not_found: 53 |
| `pass_rate` | 0.871 | 0.881 | 0.842 | 0.832 |
| `status_accuracy` | 0.881 | 0.881 | 0.851 | 0.847 |
| `auto_coverage` | 0.332 | 0.332 | 0.277 | 0.292 |
| `auto_correct` | 65 | 67 | 54 | 56 |
| `auto_incorrect` | 2 | 0 | 2 | 3 |
| `auto_precision` | 0.97 | 1 | 0.964 | 0.949 |
| `error_upper95` | — | 0.045 | — | — |
| `required_auto_hit` | 0.763 | 0.746 | 0.627 | 0.61 |
| `forbidden_auto_violations` | 3 | 3 | 3 | 4 |
| `forbidden_code_hits` | 2 | 0 | 2 | 3 |
| `compatible_recall` | 0.772 | 0.754 | 0.743 | 0.731 |
| `checks_pass` | 0.978 | 0.934 | 0.934 | 0.934 |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `checks.same_as` | 89 / 91 | 85 / 91 | 85 / 91 | 85 / 91 |
| `dialog_resolved` | 0.644 | 0.567 | 0.6 | 0.562 |
| `dialog_cases` | 104 | 104 | 115 | 112 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 1.82 | 1.81 | 1.83 | 1.89 |
| `latency_ms.p50` | 6.27 | 7.87 | 12.44 | 7.02 |
| `latency_ms.p95` | 26.5 | 25.09 | 43.81 | 21.7 |
| `latency_ms.max` | 155.64 | 66.46 | 268.46 | 64.58 |
| `latency_ms.mean` | 9.24 | 10.29 | 17.85 | 8.86 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | 0.22 | 0.254 | 0.356 | 0.356 |
| `ranking.ranked_cases` | 171 | 171 | 171 | 171 |
| `ranking.hit@1` | 0.684 | 0.696 | 0.637 | 0.643 |
| `ranking.hit@3` | 0.754 | 0.731 | 0.719 | 0.713 |
| `ranking.hit@5` | 0.766 | 0.749 | 0.737 | 0.725 |
| `ranking.mrr` | 0.72 | 0.716 | 0.679 | 0.678 |
| `ranking.ndcg@3` | 0.726 | 0.714 | 0.683 | 0.673 |
| `ranking.type_hit@1` | 0.772 | 0.76 | 0.76 | 0.76 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.228 | 0.246 | 0.257 | 0.269 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.848 | 0.871 | 0.816 | 0.822 |
| `ranking.dialog_traced` | 171 | 171 | 171 | 171 |
| `ranking.mrr_by_step` | 0.72 → 0.762 → 0.775 → 0.778 → 0.778 → 0.778 → 0.778 | 0.716 → 0.741 → 0.754 → 0.754 → 0.754 → 0.754 → 0.754 | 0.679 → 0.726 → 0.739 → 0.739 → 0.739 → 0.739 → 0.739 | 0.678 → 0.724 → 0.734 → 0.737 → 0.737 → 0.737 → 0.737 |
| `ranking.hit1_by_step` | 0.684 → 0.749 → 0.772 → 0.778 → 0.778 → 0.778 → 0.778 | 0.696 → 0.731 → 0.754 → 0.754 → 0.754 → 0.754 → 0.754 | 0.637 → 0.713 → 0.737 → 0.737 → 0.737 → 0.737 → 0.737 | 0.643 → 0.713 → 0.731 → 0.737 → 0.737 → 0.737 → 0.737 |
| `ranking.rank_by_step` | 1.26 → 1.05 → 1.01 → 1 → 1 → 1 → 1 | 1.24 → 1.05 → 1 → 1 → 1 → 1 → 1 | 1.32 → 1.06 → 1.02 → 1.02 → 1.02 → 1.02 → 1.02 | 1.28 → 1.05 → 1.01 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 0.778 | 0.754 | 0.737 | 0.737 |
| `ranking.questions_to_top1_mean` | 0.17 | 0.11 | 0.17 | 0.17 |
| `ranking.bits_per_question` | 0.702 | 0.635 | 0.625 | 0.476 |
| `ranking.useless_question_rate` | 0.535 | 0.6 | 0.607 | 0.66 |
| `ranking.dead_end_rate` | 0.035 | 0.047 | 0.047 | 0.047 |

#### stress (917 кейсов)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 917 | 917 | 917 | 917 |
| `errors` | 0 | 0 | 0 | 0 |
| `status_counts` | clarification: 586, conflict: 184, manual_choice: 7, matched: 140 | clarification: 622, conflict: 126, manual_choice: 8, matched: 159, not_found: 2 | clarification: 633, conflict: 120, manual_choice: 8, matched: 154, not_found: 2 | clarification: 613, conflict: 140, manual_choice: 8, matched: 154, not_found: 2 |
| `pass_rate` | 1 | 0.956 | 0.956 | 0.939 |
| `status_accuracy` | 1 | 0.956 | 0.956 | 0.942 |
| `auto_coverage` | 0.153 | 0.173 | 0.168 | 0.168 |
| `auto_correct` | 140 | 158 | 153 | 151 |
| `auto_incorrect` | 0 | 1 | 1 | 3 |
| `auto_precision` | 1 | 0.994 | 0.994 | 0.981 |
| `error_upper95` | 0.021 | — | — | — |
| `required_auto_hit` | — | — | — | — |
| `forbidden_auto_violations` | 0 | 28 | 28 | 28 |
| `forbidden_code_hits` | 0 | 0 | 0 | 0 |
| `compatible_recall` | 0.992 | 0.977 | 0.97 | 0.95 |
| `checks_pass` | — | — | — | — |
| `checks_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_resolved` | 0.969 | 0.934 | 0.909 | 0.914 |
| `dialog_cases` | 653 | 635 | 640 | 639 |
| `dialog_not_supported` | 0 | 0 | 0 | 0 |
| `dialog_steps_mean` | 2.01 | 1.98 | 1.99 | 1.96 |
| `latency_ms.p50` | 4.69 | 6.37 | 14.15 | 4.73 |
| `latency_ms.p95` | 11.16 | 15.49 | 31.02 | 12.68 |
| `latency_ms.max` | 199.03 | 51.6 | 204.45 | 46.78 |
| `latency_ms.mean` | 6.3 | 7.73 | 16.33 | 6.03 |
| `determinism` | 1 | 1 | 1 | 1 |
| `over_asking` | — | — | — | — |
| `ranking.ranked_cases` | 793 | 793 | 793 | 793 |
| `ranking.hit@1` | 0.962 | 0.931 | 0.916 | 0.919 |
| `ranking.hit@3` | 0.987 | 0.966 | 0.958 | 0.945 |
| `ranking.hit@5` | 0.992 | 0.977 | 0.97 | 0.95 |
| `ranking.mrr` | 0.974 | 0.948 | 0.937 | 0.931 |
| `ranking.ndcg@3` | 0.973 | 0.947 | 0.937 | 0.93 |
| `ranking.type_hit@1` | 1 | 0.984 | 0.984 | 0.967 |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 |
| `ranking.gold_not_listed` | 0.008 | 0.023 | 0.03 | 0.05 |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 |
| `ranking.list_precision_mean` | 0.976 | 0.963 | 0.952 | 0.965 |
| `ranking.dialog_traced` | 793 | 793 | 793 | 793 |
| `ranking.mrr_by_step` | 0.974 → 0.992 → 0.992 → 0.992 → 0.992 → 0.992 → 0.992 | 0.948 → 0.974 → 0.974 → 0.974 → 0.974 → 0.974 → 0.974 | 0.937 → 0.967 → 0.967 → 0.967 → 0.967 → 0.967 → 0.967 | 0.931 → 0.95 → 0.95 → 0.95 → 0.95 → 0.95 → 0.95 |
| `ranking.hit1_by_step` | 0.962 → 0.992 → 0.992 → 0.992 → 0.992 → 0.992 → 0.992 | 0.931 → 0.971 → 0.971 → 0.971 → 0.971 → 0.971 → 0.971 | 0.916 → 0.963 → 0.963 → 0.963 → 0.963 → 0.963 → 0.963 | 0.919 → 0.95 → 0.95 → 0.95 → 0.95 → 0.95 → 0.95 |
| `ranking.rank_by_step` | 1.05 → 1 → 1 → 1 → 1 → 1 → 1 | 1.09 → 1.01 → 1.01 → 1.01 → 1.01 → 1.01 → 1.01 | 1.1 → 1.01 → 1.01 → 1.01 → 1.01 → 1.01 → 1.01 | 1.06 → 1 → 1 → 1 → 1 → 1 → 1 |
| `ranking.top1_reached` | 0.992 | 0.971 | 0.963 | 0.95 |
| `ranking.questions_to_top1_mean` | 0.03 | 0.04 | 0.05 | 0.03 |
| `ranking.bits_per_question` | 0.111 | 0.143 | 0.131 | 0.119 |
| `ranking.useless_question_rate` | 0.894 | 0.872 | 0.882 | 0.887 |
| `ranking.dead_end_rate` | 0.008 | 0.006 | 0.014 | 0.014 |

## 2. `benchmark.independent.run`: метрики v2

Независимые наборы — по test-части (заморожена); метаморфные — по всем кейсам. Колонки справа — тривиальные базовые линии (минимум, который получает решение, ничего не делающее). ДИ — 95%, бутстреп или «правило трёх».

#### natural — test (313)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 313 | 313 | 313 | 313 | 313 | 313 |
| `status_counts` | clarification: 161, conflict: 13, manual_choice: 2, matched: 136, not_found: 1 | clarification: 149, conflict: 19, manual_choice: 2, matched: 142, not_found: 1 | clarification: 181, conflict: 13, manual_choice: 2, matched: 116, not_found: 1 | clarification: 177, conflict: 16, manual_choice: 2, matched: 117, not_found: 1 | clarification: 313 | not_found: 313 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 136 | 142 | 116 | 117 | 0 | 0 |
| `wrong_auto` | 5 | 1 | 4 | 6 | 0 | 0 |
| `wrong_auto_rate` | 0.037 | 0.007 | 0.035 | 0.051 | — | — |
| `auto_precision` | 0.963 | 0.993 | 0.966 | 0.949 | — | — |
| `auto_coverage` | 0.434 | 0.454 | 0.371 | 0.374 | 0 | 0 |
| `gold_nonempty` | 313 | 313 | 313 | 313 | 313 | 313 |
| `code_reached@0` | 0.418 | 0.451 | 0.358 | 0.355 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.754 | 0.76 | 0.684 | 0.674 | 0 | 0 |
| `code_reached@2` | 0.844 | 0.821 | 0.783 | 0.776 | 0 | 0 |
| `code_reached@3` | 0.888 | 0.85 | 0.821 | 0.815 | 0 | 0 |
| `required_cases` | 189 | 189 | 189 | 189 | 189 | 189 |
| `required_hit` | 0.693 | 0.746 | 0.593 | 0.577 | 0 | 0 |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0 | 0 | 0.029 | 0 | 0 |
| `dialog_wrong_final` | 5 | 1 | 4 | 6 | 0 | 0 |
| `questions_mean` | 0.73 | 0.609 | 0.778 | 0.784 | — | — |
| `latency_ms_p50` | 7.3 | 10.32 | 18.67 | 8.45 | 0 | 0 |
| `latency_ms_p95` | 20.22 | 24.56 | 36.53 | 21.52 | 0 | 0 |
| `ci95.code_reached@2` | 0.802–0.882 (n=313) | 0.776–0.863 (n=313) | 0.738–0.828 (n=313) | 0.732–0.821 (n=313) | 0–0.01 (n=313) | 0–0.01 (n=313) |
| `ci95.auto_precision` | 0.926–0.993 (n=136) | 0.979–1 (n=142) | 0.931–0.991 (n=116) | 0.906–0.983 (n=117) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.859–0.926 (n=313) | 0.872–0.939 (n=313) | 0.821–0.898 (n=313) | 0.811–0.891 (n=313) | — | — |
| `ci95.hit@3` | 0.914–0.965 (n=313) | 0.891–0.952 (n=313) | 0.885–0.949 (n=313) | 0.875–0.939 (n=313) | — | — |
| `wrong_auto_rate_upper95` | 0.073 | 0.021 | 0.069 | 0.094 | — | — |
| `ranking.ranked_cases` | 313 | 313 | 313 | 313 | 0 | 0 |
| `ranking.hit@1` | 0.895 | 0.907 | 0.859 | 0.853 | — | — |
| `ranking.hit@3` | 0.939 | 0.923 | 0.917 | 0.907 | — | — |
| `ranking.hit@5` | 0.949 | 0.93 | 0.93 | 0.917 | — | — |
| `ranking.mrr` | 0.919 | 0.917 | 0.891 | 0.882 | — | — |
| `ranking.ndcg@3` | 0.92 | 0.915 | 0.893 | 0.881 | — | — |
| `ranking.type_hit@1` | 0.971 | 0.933 | 0.952 | 0.942 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.045 | 0.07 | 0.064 | 0.077 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.912 | 0.973 | 0.893 | 0.9 | — | — |
| `ranking.dialog_traced` | 313 | 313 | 313 | 313 | 0 | 0 |
| `ranking.mrr_by_step` | 0.919 → 0.958 → 0.96 → 0.962 | 0.917 → 0.927 → 0.93 → 0.93 | 0.891 → 0.931 → 0.936 → 0.936 | 0.882 → 0.918 → 0.923 → 0.923 | — | — |
| `ranking.hit1_by_step` | 0.895 → 0.955 → 0.958 → 0.962 | 0.907 → 0.927 → 0.93 → 0.93 | 0.859 → 0.927 → 0.936 → 0.936 | 0.853 → 0.914 → 0.923 → 0.923 | — | — |
| `ranking.rank_by_step` | 1.14 → 1.01 → 1 → 1 | 1.04 → 1.01 → 1 → 1 | 1.16 → 1.01 → 1 → 1 | 1.15 → 1.01 → 1 → 1 | — | — |
| `ranking.top1_reached` | 0.962 | 0.93 | 0.936 | 0.923 | — | — |
| `ranking.questions_to_top1_mean` | 0.08 | 0.03 | 0.09 | 0.09 | — | — |
| `ranking.bits_per_question` | 0.583 | 0.527 | 0.55 | 0.514 | — | — |
| `ranking.useless_question_rate` | 0.578 | 0.64 | 0.611 | 0.626 | — | — |
| `ranking.dead_end_rate` | 0.003 | 0.003 | 0.003 | 0 | — | — |
| `over_asking` | 0.28 | 0.249 | 0.386 | 0.392 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### natural — dev (по нему настраивалась `Lenaz`)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 760 | 760 | 760 | 760 |
| `wrong_auto` | 9 | 0 | 9 | 8 |
| `auto_precision` | 0.973 | 1 | 0.969 | 0.974 |
| `code_reached@0` | 0.422 | 0.466 | 0.375 | 0.399 |
| `code_reached@2` | 0.815 | 0.853 | 0.771 | 0.792 |
| `required_hit` | 0.676 | 0.744 | 0.6 | 0.625 |
| `no_code_respected` | — | — | — | — |

#### contradictions — test (102)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 102 | 102 | 102 | 102 | 102 | 102 |
| `status_counts` | clarification: 6, conflict: 90, matched: 6 | clarification: 7, conflict: 93, matched: 2 | clarification: 8, conflict: 85, matched: 9 | clarification: 9, conflict: 87, matched: 6 | clarification: 102 | not_found: 102 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 6 | 2 | 9 | 6 | 0 | 0 |
| `wrong_auto` | 6 | 2 | 9 | 6 | 0 | 0 |
| `wrong_auto_rate` | 1 | 1 | 1 | 1 | — | — |
| `auto_precision` | 0 | 0 | 0 | 0 | — | — |
| `auto_coverage` | 0.059 | 0.02 | 0.088 | 0.059 | 0 | 0 |
| `gold_nonempty` | 0 | 0 | 0 | 0 | 0 | 0 |
| `code_reached@0` | — | — | — | — | — | — |
| `dialog_support` | not_run | not_run | not_run | not_run | not_run | not_run |
| `code_reached@1` | — | — | — | — | — | — |
| `code_reached@2` | — | — | — | — | — | — |
| `code_reached@3` | — | — | — | — | — | — |
| `required_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `required_hit` | — | — | — | — | — | — |
| `no_code_cases` | 102 | 102 | 102 | 102 | 102 | 102 |
| `no_code_respected` | 0.941 | 0.98 | 0.912 | 0.941 | 1 | 1 |
| `premature_auto` | — | — | — | — | — | — |
| `dialog_wrong_final` | 0 | 0 | 0 | 0 | 0 | 0 |
| `questions_mean` | — | — | — | — | — | — |
| `latency_ms_p50` | 6.07 | 9.94 | 17.02 | 9.06 | 0 | 0 |
| `latency_ms_p95` | 16.18 | 23.32 | 34.94 | 23.72 | 0 | 0 |
| `ci95.code_reached@2` | — | — | — | — | — | — |
| `ci95.auto_precision` | 0–0.5 (n=6) | 0–1 (n=2) | 0–0.333 (n=9) | 0–0.5 (n=6) | — | — |
| `ci95.no_code_respected` | 0.892–0.98 (n=102) | 0.951–1 (n=102) | 0.853–0.961 (n=102) | 0.892–0.98 (n=102) | 0.971–1 (n=102) | 0.971–1 (n=102) |
| `ci95.hit@1` | — | — | — | — | — | — |
| `ci95.hit@3` | — | — | — | — | — | — |
| `wrong_auto_rate_upper95` | 1 | 1 | 1 | 1 | — | — |
| `ranking.ranked_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `ranking.dialog_traced` | 0 | 0 | 0 | 0 | 0 | 0 |
| `over_asking` | — | — | — | — | — | — |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### contradictions — dev (по нему настраивалась `Lenaz`)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 241 | 241 | 241 | 241 |
| `wrong_auto` | 20 | 9 | 28 | 26 |
| `auto_precision` | 0 | 0 | 0 | 0 |
| `code_reached@0` | — | — | — | — |
| `code_reached@2` | — | — | — | — |
| `required_hit` | — | — | — | — |
| `no_code_respected` | 0.917 | 0.963 | 0.884 | 0.892 |

#### out_of_scope — test (32)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 32 | 32 | 32 | 32 | 32 | 32 |
| `status_counts` | not_found: 32 | not_found: 32 | not_found: 32 | not_found: 32 | clarification: 32 | not_found: 32 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `wrong_auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `wrong_auto_rate` | — | — | — | — | — | — |
| `auto_precision` | — | — | — | — | — | — |
| `auto_coverage` | 0 | 0 | 0 | 0 | 0 | 0 |
| `gold_nonempty` | 0 | 0 | 0 | 0 | 0 | 0 |
| `code_reached@0` | — | — | — | — | — | — |
| `dialog_support` | not_run | not_run | not_run | not_run | not_run | not_run |
| `code_reached@1` | — | — | — | — | — | — |
| `code_reached@2` | — | — | — | — | — | — |
| `code_reached@3` | — | — | — | — | — | — |
| `required_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `required_hit` | — | — | — | — | — | — |
| `no_code_cases` | 32 | 32 | 32 | 32 | 32 | 32 |
| `no_code_respected` | 1 | 1 | 1 | 1 | 1 | 1 |
| `premature_auto` | — | — | — | — | — | — |
| `dialog_wrong_final` | 0 | 0 | 0 | 0 | 0 | 0 |
| `questions_mean` | — | — | — | — | — | — |
| `latency_ms_p50` | 2.06 | 2.3 | 2.12 | 2.24 | 0 | 0 |
| `latency_ms_p95` | 3.44 | 3.22 | 2.97 | 3.31 | 0 | 0 |
| `ci95.code_reached@2` | — | — | — | — | — | — |
| `ci95.auto_precision` | — | — | — | — | — | — |
| `ci95.no_code_respected` | 0.906–1 (n=32) | 0.906–1 (n=32) | 0.906–1 (n=32) | 0.906–1 (n=32) | 0.906–1 (n=32) | 0.906–1 (n=32) |
| `ci95.hit@1` | — | — | — | — | — | — |
| `ci95.hit@3` | — | — | — | — | — | — |
| `wrong_auto_rate_upper95` | — | — | — | — | — | — |
| `ranking.ranked_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `ranking.dialog_traced` | 0 | 0 | 0 | 0 | 0 | 0 |
| `over_asking` | — | — | — | — | — | — |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### out_of_scope — dev (по нему настраивалась `Lenaz`)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` |
|---|---|---|---|---|
| `cases` | 66 | 66 | 66 | 66 |
| `wrong_auto` | 0 | 1 | 1 | 1 |
| `auto_precision` | — | 0 | 0 | 0 |
| `code_reached@0` | — | — | — | — |
| `code_reached@2` | — | — | — | — |
| `required_hit` | — | — | — | — |
| `no_code_respected` | 1 | 0.985 | 0.985 | 0.985 |

#### edge_inputs — все кейсы (39)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 39 | 39 | 39 | 39 | 39 | 39 |
| `status_counts` | clarification: 2, not_found: 37 | clarification: 2, not_found: 37 | clarification: 2, not_found: 37 | clarification: 2, not_found: 37 | clarification: 39 | not_found: 39 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `wrong_auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `wrong_auto_rate` | — | — | — | — | — | — |
| `auto_precision` | — | — | — | — | — | — |
| `auto_coverage` | 0 | 0 | 0 | 0 | 0 | 0 |
| `gold_nonempty` | 0 | 0 | 0 | 0 | 0 | 0 |
| `code_reached@0` | — | — | — | — | — | — |
| `dialog_support` | not_run | not_run | not_run | not_run | not_run | not_run |
| `code_reached@1` | — | — | — | — | — | — |
| `code_reached@2` | — | — | — | — | — | — |
| `code_reached@3` | — | — | — | — | — | — |
| `required_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `required_hit` | — | — | — | — | — | — |
| `no_code_cases` | 39 | 39 | 39 | 39 | 39 | 39 |
| `no_code_respected` | 1 | 1 | 1 | 1 | 1 | 1 |
| `premature_auto` | — | — | — | — | — | — |
| `dialog_wrong_final` | 0 | 0 | 0 | 0 | 0 | 0 |
| `questions_mean` | — | — | — | — | — | — |
| `latency_ms_p50` | 0.69 | 0.79 | 0.86 | 0.29 | 0 | 0 |
| `latency_ms_p95` | 9.73 | 11.24 | 10.22 | 6.66 | 0 | 0 |
| `ci95.code_reached@2` | — | — | — | — | — | — |
| `ci95.auto_precision` | — | — | — | — | — | — |
| `ci95.no_code_respected` | 0.923–1 (n=39) | 0.923–1 (n=39) | 0.923–1 (n=39) | 0.923–1 (n=39) | 0.923–1 (n=39) | 0.923–1 (n=39) |
| `ci95.hit@1` | — | — | — | — | — | — |
| `ci95.hit@3` | — | — | — | — | — | — |
| `wrong_auto_rate_upper95` | — | — | — | — | — | — |
| `ranking.ranked_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `ranking.dialog_traced` | 0 | 0 | 0 | 0 | 0 | 0 |
| `over_asking` | — | — | — | — | — | — |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### glued_words — все кейсы (100)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 100 | 100 | 100 | 100 | 100 | 100 |
| `status_counts` | clarification: 45, conflict: 1, manual_choice: 2, matched: 26, not_found: 26 | clarification: 44, conflict: 1, manual_choice: 1, matched: 12, not_found: 42 | clarification: 47, manual_choice: 1, matched: 10, not_found: 42 | clarification: 46, conflict: 1, manual_choice: 1, matched: 10, not_found: 42 | clarification: 100 | not_found: 100 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 26 | 12 | 10 | 10 | 0 | 0 |
| `wrong_auto` | 1 | 1 | 2 | 3 | 0 | 0 |
| `wrong_auto_rate` | 0.038 | 0.083 | 0.2 | 0.3 | — | — |
| `auto_precision` | 0.962 | 0.917 | 0.8 | 0.7 | — | — |
| `auto_coverage` | 0.26 | 0.12 | 0.1 | 0.1 | 0 | 0 |
| `gold_nonempty` | 100 | 100 | 100 | 100 | 100 | 100 |
| `code_reached@0` | 0.25 | 0.11 | 0.08 | 0.07 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.37 | 0.2 | 0.18 | 0.17 | 0 | 0 |
| `code_reached@2` | 0.49 | 0.29 | 0.26 | 0.24 | 0 | 0 |
| `code_reached@3` | 0.6 | 0.34 | 0.36 | 0.34 | 0 | 0 |
| `required_cases` | 64 | 64 | 64 | 64 | 64 | 64 |
| `required_hit` | 0.391 | 0.172 | 0.125 | 0.109 | 0 | 0 |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0.042 | 0.042 | 0.042 | 0 | 0 |
| `dialog_wrong_final` | 1 | 1 | 2 | 3 | 0 | 0 |
| `questions_mean` | 1.15 | 1.235 | 1.556 | 1.588 | — | — |
| `latency_ms_p50` | 9.47 | 10.55 | 15.39 | 9.04 | 0 | 0 |
| `latency_ms_p95` | 77.58 | 208.17 | 235.79 | 176.83 | 0 | 0 |
| `ci95.code_reached@2` | 0.39–0.59 (n=100) | 0.2–0.38 (n=100) | 0.18–0.34 (n=100) | 0.16–0.32 (n=100) | 0–0.03 (n=100) | 0–0.03 (n=100) |
| `ci95.auto_precision` | 0.885–1 (n=26) | 0.75–1 (n=12) | 0.5–1 (n=10) | 0.4–0.9 (n=10) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.49–0.67 (n=100) | 0.23–0.41 (n=100) | 0.23–0.41 (n=100) | 0.21–0.39 (n=100) | — | — |
| `ci95.hit@3` | 0.57–0.75 (n=100) | 0.31–0.51 (n=100) | 0.33–0.52 (n=100) | 0.31–0.5 (n=100) | — | — |
| `wrong_auto_rate_upper95` | 0.115 | 0.25 | 0.5 | 0.6 | — | — |
| `ranking.ranked_cases` | 100 | 100 | 100 | 100 | 0 | 0 |
| `ranking.hit@1` | 0.58 | 0.32 | 0.32 | 0.3 | — | — |
| `ranking.hit@3` | 0.66 | 0.41 | 0.42 | 0.4 | — | — |
| `ranking.hit@5` | 0.69 | 0.45 | 0.46 | 0.44 | — | — |
| `ranking.mrr` | 0.628 | 0.376 | 0.382 | 0.362 | — | — |
| `ranking.ndcg@3` | 0.623 | 0.372 | 0.378 | 0.358 | — | — |
| `ranking.type_hit@1` | 0.69 | 0.43 | 0.45 | 0.43 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.29 | 0.53 | 0.5 | 0.52 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.683 | 0.474 | 0.434 | 0.423 | — | — |
| `ranking.dialog_traced` | 100 | 100 | 100 | 100 | 0 | 0 |
| `ranking.mrr_by_step` | 0.628 → 0.68 → 0.703 → 0.703 | 0.376 → 0.431 → 0.446 → 0.446 | 0.382 → 0.453 → 0.486 → 0.486 | 0.362 → 0.433 → 0.466 → 0.466 | — | — |
| `ranking.hit1_by_step` | 0.58 → 0.66 → 0.7 → 0.7 | 0.32 → 0.4 → 0.43 → 0.43 | 0.32 → 0.42 → 0.48 → 0.48 | 0.3 → 0.4 → 0.46 → 0.46 | — | — |
| `ranking.rank_by_step` | 2.08 → 1.13 → 1.03 → 1.03 | 1.79 → 1.21 → 1.15 → 1.15 | 3 → 1.28 → 1.1 → 1.1 | 3.08 → 1.29 → 1.1 → 1.1 | — | — |
| `ranking.top1_reached` | 0.7 | 0.43 | 0.48 | 0.46 | — | — |
| `ranking.questions_to_top1_mean` | 0.23 | 0.33 | 0.46 | 0.48 | — | — |
| `ranking.bits_per_question` | 0.791 | 0.849 | 0.973 | 0.954 | — | — |
| `ranking.useless_question_rate` | 0.461 | 0.538 | 0.432 | 0.43 | — | — |
| `ranking.dead_end_rate` | 0.02 | 0.09 | 0.06 | 0.06 | — | — |
| `over_asking` | 0.594 | 0.828 | 0.859 | 0.859 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### injection — все кейсы (105)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 105 | 105 | 105 | 105 | 105 | 105 |
| `status_counts` | clarification: 55, conflict: 1, manual_choice: 6, matched: 43 | clarification: 48, conflict: 5, manual_choice: 5, matched: 47 | clarification: 61, conflict: 3, manual_choice: 5, matched: 36 | clarification: 63, conflict: 4, manual_choice: 4, matched: 34 | clarification: 105 | not_found: 105 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 43 | 47 | 36 | 34 | 0 | 0 |
| `wrong_auto` | 3 | 0 | 3 | 2 | 0 | 0 |
| `wrong_auto_rate` | 0.07 | 0 | 0.083 | 0.059 | — | — |
| `auto_precision` | 0.93 | 1 | 0.917 | 0.941 | — | — |
| `auto_coverage` | 0.409 | 0.448 | 0.343 | 0.324 | 0 | 0 |
| `gold_nonempty` | 105 | 105 | 105 | 105 | 105 | 105 |
| `code_reached@0` | 0.381 | 0.448 | 0.314 | 0.305 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.676 | 0.695 | 0.581 | 0.581 | 0 | 0 |
| `code_reached@2` | 0.771 | 0.867 | 0.743 | 0.743 | 0 | 0 |
| `code_reached@3` | 0.905 | 0.905 | 0.848 | 0.838 | 0 | 0 |
| `required_cases` | 76 | 76 | 76 | 76 | 76 | 76 |
| `required_hit` | 0.526 | 0.618 | 0.434 | 0.421 | 0 | 0 |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `dialog_wrong_final` | 3 | 0 | 3 | 2 | 0 | 0 |
| `questions_mean` | 0.979 | 0.779 | 1.067 | 1.057 | — | — |
| `latency_ms_p50` | 9.12 | 14.24 | 20.58 | 13.54 | 0 | 0 |
| `latency_ms_p95` | 33.27 | 31.95 | 44.09 | 27.85 | 0 | 0 |
| `ci95.code_reached@2` | 0.686–0.848 (n=105) | 0.8–0.924 (n=105) | 0.657–0.829 (n=105) | 0.657–0.819 (n=105) | 0–0.029 (n=105) | 0–0.029 (n=105) |
| `ci95.auto_precision` | 0.861–1 (n=43) | 0.936–1 (n=47) | 0.806–1 (n=36) | 0.853–1 (n=34) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.657–0.819 (n=105) | 0.8–0.924 (n=105) | 0.61–0.79 (n=105) | 0.629–0.8 (n=105) | — | — |
| `ci95.hit@3` | 0.857–0.962 (n=105) | 0.857–0.962 (n=105) | 0.809–0.933 (n=105) | 0.8–0.924 (n=105) | — | — |
| `wrong_auto_rate_upper95` | 0.14 | 0.064 | 0.194 | 0.147 | — | — |
| `ranking.ranked_cases` | 105 | 105 | 105 | 105 | 0 | 0 |
| `ranking.hit@1` | 0.743 | 0.867 | 0.705 | 0.714 | — | — |
| `ranking.hit@3` | 0.914 | 0.914 | 0.876 | 0.867 | — | — |
| `ranking.hit@5` | 0.924 | 0.933 | 0.895 | 0.886 | — | — |
| `ranking.mrr` | 0.829 | 0.897 | 0.795 | 0.797 | — | — |
| `ranking.ndcg@3` | 0.845 | 0.897 | 0.808 | 0.807 | — | — |
| `ranking.type_hit@1` | 0.99 | 0.952 | 0.971 | 0.962 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.038 | 0.048 | 0.057 | 0.067 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.765 | 0.927 | 0.748 | 0.762 | — | — |
| `ranking.dialog_traced` | 105 | 105 | 105 | 105 | 0 | 0 |
| `ranking.mrr_by_step` | 0.829 → 0.935 → 0.962 → 0.962 | 0.897 → 0.935 → 0.946 → 0.946 | 0.795 → 0.902 → 0.93 → 0.93 | 0.797 → 0.89 → 0.918 → 0.918 | — | — |
| `ranking.hit1_by_step` | 0.743 → 0.914 → 0.962 → 0.962 | 0.867 → 0.924 → 0.943 → 0.943 | 0.705 → 0.876 → 0.924 → 0.924 | 0.714 → 0.867 → 0.914 → 0.914 | — | — |
| `ranking.rank_by_step` | 1.94 → 1.08 → 1 → 1 | 1.29 → 1.05 → 1.02 → 1.02 | 2.06 → 1.13 → 1.04 → 1.04 | 2.04 → 1.21 → 1.12 → 1.12 | — | — |
| `ranking.top1_reached` | 0.962 | 0.943 | 0.924 | 0.914 | — | — |
| `ranking.questions_to_top1_mean` | 0.28 | 0.1 | 0.29 | 0.27 | — | — |
| `ranking.bits_per_question` | 0.638 | 0.351 | 0.578 | 0.538 | — | — |
| `ranking.useless_question_rate` | 0.559 | 0.742 | 0.608 | 0.62 | — | — |
| `ranking.dead_end_rate` | 0 | 0 | 0 | 0.01 | — | — |
| `over_asking` | 0.434 | 0.382 | 0.526 | 0.553 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### invariance — все кейсы (480)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 480 | 480 | 480 | 480 | 480 | 480 |
| `status_counts` | clarification: 244, conflict: 13, manual_choice: 14, matched: 209 | clarification: 211, conflict: 17, manual_choice: 10, matched: 222, not_found: 20 | clarification: 268, conflict: 5, manual_choice: 10, matched: 177, not_found: 20 | clarification: 265, conflict: 5, manual_choice: 10, matched: 180, not_found: 20 | clarification: 480 | not_found: 480 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 209 | 222 | 177 | 180 | 0 | 0 |
| `wrong_auto` | 5 | 0 | 5 | 5 | 0 | 0 |
| `wrong_auto_rate` | 0.024 | 0 | 0.028 | 0.028 | — | — |
| `auto_precision` | 0.976 | 1 | 0.972 | 0.972 | — | — |
| `auto_coverage` | 0.435 | 0.463 | 0.369 | 0.375 | 0 | 0 |
| `gold_nonempty` | 480 | 480 | 480 | 480 | 480 | 480 |
| `code_reached@0` | 0.425 | 0.463 | 0.358 | 0.365 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.738 | 0.719 | 0.613 | 0.64 | 0 | 0 |
| `code_reached@2` | 0.823 | 0.802 | 0.731 | 0.752 | 0 | 0 |
| `code_reached@3` | 0.917 | 0.846 | 0.806 | 0.827 | 0 | 0 |
| `required_cases` | 333 | 333 | 333 | 333 | 333 | 333 |
| `required_hit` | 0.613 | 0.664 | 0.516 | 0.519 | 0 | 0 |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0 | 0 | 0.013 | 0 | 0 |
| `dialog_wrong_final` | 5 | 0 | 5 | 5 | 0 | 0 |
| `questions_mean` | 0.834 | 0.655 | 0.889 | 0.877 | — | — |
| `latency_ms_p50` | 7.31 | 12.24 | 18.87 | 10.78 | 0 | 0 |
| `latency_ms_p95` | 20.82 | 29.27 | 40.51 | 24.63 | 0 | 0 |
| `ci95.code_reached@2` | 0.787–0.856 (n=480) | 0.767–0.835 (n=480) | 0.694–0.771 (n=480) | 0.715–0.79 (n=480) | 0–0.006 (n=480) | 0–0.006 (n=480) |
| `ci95.auto_precision` | 0.957–0.995 (n=209) | 0.987–1 (n=222) | 0.944–0.994 (n=177) | 0.944–0.994 (n=180) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.854–0.91 (n=480) | 0.838–0.896 (n=480) | 0.767–0.833 (n=480) | 0.777–0.844 (n=480) | — | — |
| `ci95.hit@3` | 0.931–0.971 (n=480) | 0.86–0.917 (n=480) | 0.856–0.912 (n=480) | 0.856–0.912 (n=480) | — | — |
| `wrong_auto_rate_upper95` | 0.043 | 0.013 | 0.057 | 0.056 | — | — |
| `ranking.ranked_cases` | 480 | 480 | 480 | 480 | 0 | 0 |
| `ranking.hit@1` | 0.881 | 0.867 | 0.8 | 0.81 | — | — |
| `ranking.hit@3` | 0.952 | 0.89 | 0.885 | 0.885 | — | — |
| `ranking.hit@5` | 0.967 | 0.912 | 0.91 | 0.908 | — | — |
| `ranking.mrr` | 0.918 | 0.884 | 0.848 | 0.852 | — | — |
| `ranking.ndcg@3` | 0.921 | 0.88 | 0.849 | 0.852 | — | — |
| `ranking.type_hit@1` | 0.996 | 0.919 | 0.944 | 0.944 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.019 | 0.081 | 0.071 | 0.073 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.874 | 0.936 | 0.83 | 0.847 | — | — |
| `ranking.dialog_traced` | 480 | 480 | 480 | 480 | 0 | 0 |
| `ranking.mrr_by_step` | 0.918 → 0.975 → 0.982 → 0.984 | 0.884 → 0.903 → 0.916 → 0.916 | 0.848 → 0.911 → 0.926 → 0.927 | 0.852 → 0.909 → 0.922 → 0.924 | — | — |
| `ranking.hit1_by_step` | 0.881 → 0.967 → 0.979 → 0.983 | 0.867 → 0.896 → 0.915 → 0.915 | 0.8 → 0.9 → 0.923 → 0.925 | 0.81 → 0.898 → 0.919 → 0.923 | — | — |
| `ranking.rank_by_step` | 1.31 → 1.03 → 1.01 → 1 | 1.18 → 1.08 → 1.01 → 1.01 | 1.41 → 1.07 → 1.01 → 1 | 1.4 → 1.12 → 1.06 → 1.05 | — | — |
| `ranking.top1_reached` | 0.983 | 0.915 | 0.925 | 0.923 | — | — |
| `ranking.questions_to_top1_mean` | 0.12 | 0.07 | 0.16 | 0.15 | — | — |
| `ranking.bits_per_question` | 0.549 | 0.514 | 0.56 | 0.529 | — | — |
| `ranking.useless_question_rate` | 0.631 | 0.691 | 0.647 | 0.647 | — | — |
| `ranking.dead_end_rate` | 0.004 | 0.004 | 0.008 | 0.008 | — | — |
| `over_asking` | 0.372 | 0.336 | 0.469 | 0.466 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### lazy_numbers — все кейсы (1173)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 1173 | 1173 | 1173 | 1173 | 1173 | 1173 |
| `status_counts` | clarification: 689, conflict: 126, manual_choice: 41, matched: 303, not_found: 14 | clarification: 806, conflict: 43, manual_choice: 49, matched: 261, not_found: 14 | clarification: 806, conflict: 39, manual_choice: 49, matched: 265, not_found: 14 | clarification: 833, conflict: 54, manual_choice: 49, matched: 223, not_found: 14 | clarification: 1173 | not_found: 1173 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 303 | 261 | 265 | 223 | 0 | 0 |
| `wrong_auto` | 58 | 60 | 61 | 52 | 0 | 0 |
| `wrong_auto_rate` | 0.191 | 0.23 | 0.23 | 0.233 | — | — |
| `auto_precision` | 0.809 | 0.77 | 0.77 | 0.767 | — | — |
| `auto_coverage` | 0.258 | 0.223 | 0.226 | 0.19 | 0 | 0 |
| `gold_nonempty` | 944 | 944 | 944 | 944 | 944 | 944 |
| `code_reached@0` | 0.26 | 0.213 | 0.216 | 0.181 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.504 | 0.447 | 0.436 | 0.426 | 0 | 0 |
| `code_reached@2` | 0.69 | 0.606 | 0.591 | 0.592 | 0 | 0 |
| `code_reached@3` | 0.805 | 0.675 | 0.664 | 0.667 | 0 | 0 |
| `required_cases` | 379 | 379 | 379 | 379 | 379 | 379 |
| `required_hit` | 0.644 | 0.528 | 0.536 | 0.449 | 0 | 0 |
| `no_code_cases` | 229 | 229 | 229 | 229 | 229 | 229 |
| `no_code_respected` | 0.755 | 0.747 | 0.742 | 0.782 | 1 | 1 |
| `premature_auto` | 0.016 | 0.016 | 0.016 | 0.016 | 0 | 0 |
| `dialog_wrong_final` | 2 | 2 | 2 | 2 | 0 | 0 |
| `questions_mean` | 1.195 | 1.124 | 1.128 | 1.203 | — | — |
| `latency_ms_p50` | 6.05 | 9.03 | 16.34 | 8.24 | 0 | 0 |
| `latency_ms_p95` | 11.33 | 14.82 | 28.91 | 13.63 | 0 | 0 |
| `ci95.code_reached@2` | 0.66–0.719 (n=944) | 0.574–0.636 (n=944) | 0.558–0.622 (n=944) | 0.56–0.623 (n=944) | 0–0.003 (n=944) | 0–0.003 (n=944) |
| `ci95.auto_precision` | 0.762–0.852 (n=303) | 0.717–0.82 (n=261) | 0.721–0.823 (n=265) | 0.709–0.821 (n=223) | — | — |
| `ci95.no_code_respected` | 0.699–0.808 (n=229) | 0.694–0.799 (n=229) | 0.686–0.795 (n=229) | 0.729–0.83 (n=229) | 0.987–1 (n=229) | 0.987–1 (n=229) |
| `ci95.hit@1` | 0.939–0.966 (n=944) | 0.914–0.947 (n=944) | 0.887–0.923 (n=944) | 0.909–0.943 (n=944) | — | — |
| `ci95.hit@3` | 0.964–0.983 (n=944) | 0.938–0.966 (n=944) | 0.942–0.969 (n=944) | 0.931–0.961 (n=944) | — | — |
| `wrong_auto_rate_upper95` | 0.238 | 0.283 | 0.279 | 0.291 | — | — |
| `ranking.ranked_cases` | 944 | 944 | 944 | 944 | 0 | 0 |
| `ranking.hit@1` | 0.952 | 0.931 | 0.906 | 0.926 | — | — |
| `ranking.hit@3` | 0.974 | 0.952 | 0.957 | 0.947 | — | — |
| `ranking.hit@5` | 0.976 | 0.954 | 0.959 | 0.949 | — | — |
| `ranking.mrr` | 0.963 | 0.942 | 0.931 | 0.936 | — | — |
| `ranking.ndcg@3` | 0.963 | 0.942 | 0.935 | 0.937 | — | — |
| `ranking.type_hit@1` | 0.98 | 0.96 | 0.964 | 0.954 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.024 | 0.044 | 0.04 | 0.05 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.959 | 0.969 | 0.953 | 0.968 | — | — |
| `ranking.dialog_traced` | 944 | 944 | 944 | 944 | 0 | 0 |
| `ranking.mrr_by_step` | 0.963 → 0.972 → 0.974 → 0.976 | 0.942 → 0.951 → 0.955 → 0.956 | 0.931 → 0.954 → 0.959 → 0.96 | 0.936 → 0.946 → 0.95 → 0.95 | — | — |
| `ranking.hit1_by_step` | 0.952 → 0.968 → 0.972 → 0.976 | 0.931 → 0.948 → 0.954 → 0.956 | 0.906 → 0.949 → 0.959 → 0.96 | 0.926 → 0.943 → 0.949 → 0.95 | — | — |
| `ranking.rank_by_step` | 1.03 → 1.01 → 1 → 1 | 1.09 → 1.02 → 1 → 1 | 1.12 → 1.02 → 1 → 1 | 1.09 → 1.02 → 1 → 1 | — | — |
| `ranking.top1_reached` | 0.976 | 0.956 | 0.96 | 0.95 | — | — |
| `ranking.questions_to_top1_mean` | 0.03 | 0.03 | 0.07 | 0.03 | — | — |
| `ranking.bits_per_question` | 0.138 | 0.154 | 0.173 | 0.152 | — | — |
| `ranking.useless_question_rate` | 0.889 | 0.883 | 0.864 | 0.885 | — | — |
| `ranking.dead_end_rate` | 0.004 | 0.002 | 0.002 | 0.002 | — | — |
| `over_asking` | 0.354 | 0.47 | 0.462 | 0.549 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### lazy_user — все кейсы (236)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 236 | 236 | 236 | 236 | 236 | 236 |
| `status_counts` | clarification: 132, conflict: 2, manual_choice: 9, matched: 92, not_found: 1 | clarification: 151, conflict: 7, manual_choice: 9, matched: 68, not_found: 1 | clarification: 160, conflict: 3, manual_choice: 9, matched: 63, not_found: 1 | clarification: 159, conflict: 5, manual_choice: 9, matched: 62, not_found: 1 | clarification: 236 | not_found: 236 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 92 | 68 | 63 | 62 | 0 | 0 |
| `wrong_auto` | 3 | 0 | 3 | 3 | 0 | 0 |
| `wrong_auto_rate` | 0.033 | 0 | 0.048 | 0.048 | — | — |
| `auto_precision` | 0.967 | 1 | 0.952 | 0.952 | — | — |
| `auto_coverage` | 0.39 | 0.288 | 0.267 | 0.263 | 0 | 0 |
| `gold_nonempty` | 236 | 236 | 236 | 236 | 236 | 236 |
| `code_reached@0` | 0.377 | 0.288 | 0.254 | 0.25 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.695 | 0.61 | 0.555 | 0.542 | 0 | 0 |
| `code_reached@2` | 0.78 | 0.763 | 0.699 | 0.72 | 0 | 0 |
| `code_reached@3` | 0.86 | 0.835 | 0.78 | 0.801 | 0 | 0 |
| `required_cases` | 111 | 111 | 111 | 111 | 111 | 111 |
| `required_hit` | 0.586 | 0.423 | 0.36 | 0.351 | 0 | 0 |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0 | 0 | 0.029 | 0 | 0 |
| `dialog_wrong_final` | 3 | 0 | 3 | 3 | 0 | 0 |
| `questions_mean` | 0.847 | 1.01 | 1.065 | 1.111 | — | — |
| `latency_ms_p50` | 7.27 | 10.94 | 16.66 | 8.52 | 0 | 0 |
| `latency_ms_p95` | 19.97 | 25.71 | 36.27 | 19.33 | 0 | 0 |
| `ci95.code_reached@2` | 0.725–0.831 (n=236) | 0.712–0.818 (n=236) | 0.64–0.758 (n=236) | 0.665–0.775 (n=236) | 0–0.013 (n=236) | 0–0.013 (n=236) |
| `ci95.auto_precision` | 0.924–1 (n=92) | 0.956–1 (n=68) | 0.889–1 (n=63) | 0.887–1 (n=62) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.852–0.932 (n=236) | 0.843–0.924 (n=236) | 0.822–0.911 (n=236) | 0.831–0.915 (n=236) | — | — |
| `ci95.hit@3` | 0.902–0.966 (n=236) | 0.881–0.953 (n=236) | 0.877–0.949 (n=236) | 0.873–0.945 (n=236) | — | — |
| `wrong_auto_rate_upper95` | 0.076 | 0.044 | 0.111 | 0.113 | — | — |
| `ranking.ranked_cases` | 236 | 236 | 236 | 236 | 0 | 0 |
| `ranking.hit@1` | 0.894 | 0.886 | 0.869 | 0.873 | — | — |
| `ranking.hit@3` | 0.936 | 0.919 | 0.915 | 0.911 | — | — |
| `ranking.hit@5` | 0.953 | 0.962 | 0.949 | 0.936 | — | — |
| `ranking.mrr` | 0.919 | 0.912 | 0.899 | 0.898 | — | — |
| `ranking.ndcg@3` | 0.916 | 0.902 | 0.892 | 0.89 | — | — |
| `ranking.type_hit@1` | 0.992 | 0.966 | 0.983 | 0.975 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.042 | 0.034 | 0.047 | 0.059 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.887 | 0.912 | 0.857 | 0.879 | — | — |
| `ranking.dialog_traced` | 236 | 236 | 236 | 236 | 0 | 0 |
| `ranking.mrr_by_step` | 0.919 → 0.956 → 0.964 → 0.964 | 0.912 → 0.943 → 0.957 → 0.966 | 0.899 → 0.943 → 0.953 → 0.953 | 0.898 → 0.93 → 0.941 → 0.941 | — | — |
| `ranking.hit1_by_step` | 0.894 → 0.945 → 0.962 → 0.962 | 0.886 → 0.928 → 0.953 → 0.966 | 0.869 → 0.932 → 0.953 → 0.953 | 0.873 → 0.919 → 0.941 → 0.941 | — | — |
| `ranking.rank_by_step` | 1.14 → 1.02 → 1 → 1 | 1.21 → 1.08 → 1.04 → 1 | 1.2 → 1.02 → 1 → 1 | 1.16 → 1.02 → 1 → 1 | — | — |
| `ranking.top1_reached` | 0.962 | 0.966 | 0.953 | 0.941 | — | — |
| `ranking.questions_to_top1_mean` | 0.09 | 0.14 | 0.11 | 0.09 | — | — |
| `ranking.bits_per_question` | 0.375 | 0.41 | 0.385 | 0.349 | — | — |
| `ranking.useless_question_rate` | 0.72 | 0.721 | 0.73 | 0.75 | — | — |
| `ranking.dead_end_rate` | 0.017 | 0 | 0.017 | 0.021 | — | — |
| `over_asking` | 0.387 | 0.577 | 0.613 | 0.631 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### monotonicity — все кейсы (120)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 120 | 120 | 120 | 120 | 120 | 120 |
| `status_counts` | clarification: 36, conflict: 6, manual_choice: 4, matched: 74 | clarification: 26, conflict: 2, manual_choice: 4, matched: 88 | clarification: 46, conflict: 1, manual_choice: 4, matched: 69 | clarification: 51, conflict: 1, manual_choice: 4, matched: 64 | clarification: 120 | not_found: 120 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 74 | 88 | 69 | 64 | 0 | 0 |
| `wrong_auto` | 4 | 1 | 4 | 4 | 0 | 0 |
| `wrong_auto_rate` | 0.054 | 0.011 | 0.058 | 0.062 | — | — |
| `auto_precision` | 0.946 | 0.989 | 0.942 | 0.938 | — | — |
| `auto_coverage` | 0.617 | 0.733 | 0.575 | 0.533 | 0 | 0 |
| `gold_nonempty` | 120 | 120 | 120 | 120 | 120 | 120 |
| `code_reached@0` | 0.583 | 0.725 | 0.542 | 0.5 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.8 | 0.875 | 0.742 | 0.725 | 0 | 0 |
| `code_reached@2` | 0.85 | 0.925 | 0.825 | 0.817 | 0 | 0 |
| `code_reached@3` | 0.892 | 0.925 | 0.85 | 0.842 | 0 | 0 |
| `required_cases` | 117 | 117 | 117 | 117 | 117 | 117 |
| `required_hit` | 0.598 | 0.744 | 0.556 | 0.513 | 0 | 0 |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `dialog_wrong_final` | 4 | 1 | 4 | 4 | 0 | 0 |
| `questions_mean` | 0.495 | 0.27 | 0.52 | 0.574 | — | — |
| `latency_ms_p50` | 7.56 | 11.29 | 17.11 | 9.54 | 0 | 0 |
| `latency_ms_p95` | 31.74 | 38.65 | 40.33 | 36.69 | 0 | 0 |
| `ci95.code_reached@2` | 0.783–0.908 (n=120) | 0.875–0.967 (n=120) | 0.758–0.892 (n=120) | 0.742–0.883 (n=120) | 0–0.025 (n=120) | 0–0.025 (n=120) |
| `ci95.auto_precision` | 0.892–0.987 (n=74) | 0.966–1 (n=88) | 0.884–0.986 (n=69) | 0.875–0.984 (n=64) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.775–0.9 (n=120) | 0.867–0.967 (n=120) | 0.733–0.867 (n=120) | 0.725–0.867 (n=120) | — | — |
| `ci95.hit@3` | 0.892–0.975 (n=120) | 0.933–0.992 (n=120) | 0.883–0.975 (n=120) | 0.883–0.975 (n=120) | — | — |
| `wrong_auto_rate_upper95` | 0.108 | 0.034 | 0.116 | 0.125 | — | — |
| `ranking.ranked_cases` | 120 | 120 | 120 | 120 | 0 | 0 |
| `ranking.hit@1` | 0.842 | 0.917 | 0.8 | 0.8 | — | — |
| `ranking.hit@3` | 0.942 | 0.967 | 0.933 | 0.933 | — | — |
| `ranking.hit@5` | 0.958 | 0.975 | 0.958 | 0.958 | — | — |
| `ranking.mrr` | 0.891 | 0.943 | 0.868 | 0.868 | — | — |
| `ranking.ndcg@3` | 0.901 | 0.948 | 0.881 | 0.881 | — | — |
| `ranking.type_hit@1` | 0.992 | 0.983 | 0.992 | 0.992 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.042 | 0.025 | 0.042 | 0.042 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.843 | 0.938 | 0.807 | 0.809 | — | — |
| `ranking.dialog_traced` | 120 | 120 | 120 | 120 | 0 | 0 |
| `ranking.mrr_by_step` | 0.891 → 0.958 → 0.963 → 0.967 | 0.943 → 0.975 → 0.975 → 0.975 | 0.868 → 0.949 → 0.958 → 0.958 | 0.868 → 0.949 → 0.958 → 0.958 | — | — |
| `ranking.hit1_by_step` | 0.842 → 0.95 → 0.958 → 0.967 | 0.917 → 0.975 → 0.975 → 0.975 | 0.8 → 0.942 → 0.958 → 0.958 | 0.8 → 0.942 → 0.958 → 0.958 | — | — |
| `ranking.rank_by_step` | 1.19 → 1.02 → 1.01 → 1 | 1.09 → 1 → 1 → 1 | 1.26 → 1.03 → 1 → 1 | 1.26 → 1.03 → 1 → 1 | — | — |
| `ranking.top1_reached` | 0.967 | 0.975 | 0.958 | 0.958 | — | — |
| `ranking.questions_to_top1_mean` | 0.16 | 0.06 | 0.18 | 0.18 | — | — |
| `ranking.bits_per_question` | 0.484 | 0.361 | 0.506 | 0.466 | — | — |
| `ranking.useless_question_rate` | 0.579 | 0.75 | 0.598 | 0.64 | — | — |
| `ranking.dead_end_rate` | 0 | 0 | 0 | 0 | — | — |
| `over_asking` | 0.367 | 0.248 | 0.41 | 0.453 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### multi_item — все кейсы (60)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 60 | 60 | 60 | 60 | 60 | 60 |
| `status_counts` | clarification: 24, conflict: 7, manual_choice: 3, matched: 26 | clarification: 34, conflict: 8, manual_choice: 3, matched: 15 | clarification: 24, conflict: 3, manual_choice: 3, matched: 30 | clarification: 21, conflict: 5, manual_choice: 3, matched: 31 | clarification: 60 | not_found: 60 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 26 | 15 | 30 | 31 | 0 | 0 |
| `wrong_auto` | 26 | 15 | 30 | 31 | 0 | 0 |
| `wrong_auto_rate` | 1 | 1 | 1 | 1 | — | — |
| `auto_precision` | 0 | 0 | 0 | 0 | — | — |
| `auto_coverage` | 0.433 | 0.25 | 0.5 | 0.517 | 0 | 0 |
| `gold_nonempty` | 0 | 0 | 0 | 0 | 0 | 0 |
| `code_reached@0` | — | — | — | — | — | — |
| `dialog_support` | not_run | not_run | not_run | not_run | not_run | not_run |
| `code_reached@1` | — | — | — | — | — | — |
| `code_reached@2` | — | — | — | — | — | — |
| `code_reached@3` | — | — | — | — | — | — |
| `required_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `required_hit` | — | — | — | — | — | — |
| `no_code_cases` | 60 | 60 | 60 | 60 | 60 | 60 |
| `no_code_respected` | 0.567 | 0.75 | 0.5 | 0.483 | 1 | 1 |
| `premature_auto` | — | — | — | — | — | — |
| `dialog_wrong_final` | 0 | 0 | 0 | 0 | 0 | 0 |
| `questions_mean` | — | — | — | — | — | — |
| `latency_ms_p50` | 16.16 | 27.23 | 28.75 | 19.13 | 0 | 0 |
| `latency_ms_p95` | 82.82 | 85.37 | 75.48 | 71.55 | 0 | 0 |
| `ci95.code_reached@2` | — | — | — | — | — | — |
| `ci95.auto_precision` | 0–0.115 (n=26) | 0–0.2 (n=15) | 0–0.1 (n=30) | 0–0.097 (n=31) | — | — |
| `ci95.no_code_respected` | 0.433–0.683 (n=60) | 0.65–0.85 (n=60) | 0.367–0.633 (n=60) | 0.35–0.617 (n=60) | 0.95–1 (n=60) | 0.95–1 (n=60) |
| `ci95.hit@1` | — | — | — | — | — | — |
| `ci95.hit@3` | — | — | — | — | — | — |
| `wrong_auto_rate_upper95` | 1 | 1 | 1 | 1 | — | — |
| `ranking.ranked_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `ranking.dialog_traced` | 0 | 0 | 0 | 0 | 0 | 0 |
| `over_asking` | — | — | — | — | — | — |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### number_errors — все кейсы (160)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 160 | 160 | 160 | 160 | 160 | 160 |
| `status_counts` | clarification: 100, conflict: 27, manual_choice: 3, matched: 30 | clarification: 92, conflict: 25, manual_choice: 6, matched: 37 | clarification: 110, conflict: 21, manual_choice: 6, matched: 23 | clarification: 107, conflict: 22, manual_choice: 5, matched: 26 | clarification: 160 | not_found: 160 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 30 | 37 | 23 | 26 | 0 | 0 |
| `wrong_auto` | 1 | 0 | 1 | 1 | 0 | 0 |
| `wrong_auto_rate` | 0.033 | 0 | 0.043 | 0.038 | — | — |
| `auto_precision` | 0.967 | 1 | 0.957 | 0.962 | — | — |
| `auto_coverage` | 0.188 | 0.231 | 0.144 | 0.163 | 0 | 0 |
| `gold_nonempty` | 160 | 160 | 160 | 160 | 160 | 160 |
| `code_reached@0` | 0.181 | 0.231 | 0.138 | 0.156 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.512 | 0.469 | 0.425 | 0.469 | 0 | 0 |
| `code_reached@2` | 0.65 | 0.613 | 0.55 | 0.594 | 0 | 0 |
| `code_reached@3` | 0.731 | 0.688 | 0.625 | 0.662 | 0 | 0 |
| `required_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `required_hit` | — | — | — | — | — | — |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `dialog_wrong_final` | 1 | 0 | 1 | 1 | 0 | 0 |
| `questions_mean` | 1.162 | 1.091 | 1.22 | 1.16 | — | — |
| `latency_ms_p50` | 8.27 | 12.63 | 18 | 10.02 | 0 | 0 |
| `latency_ms_p95` | 18.01 | 25.72 | 34.1 | 19.27 | 0 | 0 |
| `ci95.code_reached@2` | 0.575–0.725 (n=160) | 0.537–0.688 (n=160) | 0.469–0.625 (n=160) | 0.519–0.669 (n=160) | 0–0.019 (n=160) | 0–0.019 (n=160) |
| `ci95.auto_precision` | 0.9–1 (n=30) | 0.919–1 (n=37) | 0.87–1 (n=23) | 0.885–1 (n=26) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.669–0.8 (n=160) | 0.694–0.825 (n=160) | 0.619–0.762 (n=160) | 0.637–0.775 (n=160) | — | — |
| `ci95.hit@3` | 0.787–0.9 (n=160) | 0.744–0.863 (n=160) | 0.756–0.875 (n=160) | 0.744–0.863 (n=160) | — | — |
| `wrong_auto_rate_upper95` | 0.1 | 0.081 | 0.13 | 0.115 | — | — |
| `ranking.ranked_cases` | 160 | 160 | 160 | 160 | 0 | 0 |
| `ranking.hit@1` | 0.738 | 0.762 | 0.694 | 0.706 | — | — |
| `ranking.hit@3` | 0.844 | 0.806 | 0.819 | 0.806 | — | — |
| `ranking.hit@5` | 0.85 | 0.819 | 0.825 | 0.812 | — | — |
| `ranking.mrr` | 0.79 | 0.787 | 0.756 | 0.758 | — | — |
| `ranking.ndcg@3` | 0.796 | 0.785 | 0.763 | 0.761 | — | — |
| `ranking.type_hit@1` | 0.887 | 0.844 | 0.869 | 0.863 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.131 | 0.156 | 0.144 | 0.156 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.81 | 0.888 | 0.772 | 0.797 | — | — |
| `ranking.dialog_traced` | 160 | 160 | 160 | 160 | 0 | 0 |
| `ranking.mrr_by_step` | 0.79 → 0.844 → 0.863 → 0.866 | 0.787 → 0.811 → 0.819 → 0.829 | 0.756 → 0.806 → 0.824 → 0.829 | 0.758 → 0.805 → 0.82 → 0.825 | — | — |
| `ranking.hit1_by_step` | 0.738 → 0.825 → 0.856 → 0.863 | 0.762 → 0.8 → 0.812 → 0.825 | 0.694 → 0.781 → 0.812 → 0.819 | 0.706 → 0.787 → 0.812 → 0.819 | — | — |
| `ranking.rank_by_step` | 1.29 → 1.12 → 1.06 → 1.05 | 1.45 → 1.35 → 1.14 → 1.09 | 1.58 → 1.39 → 1.16 → 1.13 | 1.54 → 1.36 → 1.13 → 1.1 | — | — |
| `ranking.top1_reached` | 0.863 | 0.825 | 0.819 | 0.819 | — | — |
| `ranking.questions_to_top1_mean` | 0.2 | 0.12 | 0.21 | 0.18 | — | — |
| `ranking.bits_per_question` | 0.391 | 0.323 | 0.393 | 0.389 | — | — |
| `ranking.useless_question_rate` | 0.751 | 0.801 | 0.75 | 0.762 | — | — |
| `ranking.dead_end_rate` | 0.075 | 0.05 | 0.056 | 0.062 | — | — |
| `over_asking` | — | — | — | — | — | — |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### procurement_noise — все кейсы (105)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 105 | 105 | 105 | 105 | 105 | 105 |
| `status_counts` | clarification: 55, conflict: 2, manual_choice: 6, matched: 40, not_found: 2 | clarification: 50, conflict: 3, manual_choice: 5, matched: 47 | clarification: 59, conflict: 2, manual_choice: 5, matched: 39 | clarification: 56, conflict: 2, manual_choice: 5, matched: 42 | clarification: 105 | not_found: 105 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 40 | 47 | 39 | 42 | 0 | 0 |
| `wrong_auto` | 2 | 0 | 2 | 3 | 0 | 0 |
| `wrong_auto_rate` | 0.05 | 0 | 0.051 | 0.071 | — | — |
| `auto_precision` | 0.95 | 1 | 0.949 | 0.929 | — | — |
| `auto_coverage` | 0.381 | 0.448 | 0.371 | 0.4 | 0 | 0 |
| `gold_nonempty` | 105 | 105 | 105 | 105 | 105 | 105 |
| `code_reached@0` | 0.362 | 0.448 | 0.352 | 0.371 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.591 | 0.743 | 0.591 | 0.61 | 0 | 0 |
| `code_reached@2` | 0.714 | 0.857 | 0.752 | 0.752 | 0 | 0 |
| `code_reached@3` | 0.79 | 0.914 | 0.829 | 0.829 | 0 | 0 |
| `required_cases` | 64 | 64 | 64 | 64 | 64 | 64 |
| `required_hit` | 0.594 | 0.719 | 0.578 | 0.594 | 0 | 0 |
| `no_code_cases` | 0 | 0 | 0 | 0 | 0 | 0 |
| `no_code_respected` | — | — | — | — | — | — |
| `premature_auto` | 0 | 0 | 0 | 0 | 0 | 0 |
| `dialog_wrong_final` | 2 | 0 | 2 | 3 | 0 | 0 |
| `questions_mean` | 0.892 | 0.76 | 0.954 | 0.908 | — | — |
| `latency_ms_p50` | 8.16 | 12.88 | 16.75 | 10.93 | 0 | 0 |
| `latency_ms_p95` | 37.28 | 33.68 | 44.47 | 28.37 | 0 | 0 |
| `ci95.code_reached@2` | 0.629–0.8 (n=105) | 0.79–0.924 (n=105) | 0.667–0.829 (n=105) | 0.667–0.829 (n=105) | 0–0.029 (n=105) | 0–0.029 (n=105) |
| `ci95.auto_precision` | 0.875–1 (n=40) | 0.936–1 (n=47) | 0.872–1 (n=39) | 0.833–1 (n=42) | — | — |
| `ci95.no_code_respected` | — | — | — | — | — | — |
| `ci95.hit@1` | 0.809–0.933 (n=105) | 0.867–0.971 (n=105) | 0.781–0.914 (n=105) | 0.809–0.933 (n=105) | — | — |
| `ci95.hit@3` | 0.857–0.962 (n=105) | 0.895–0.981 (n=105) | 0.848–0.962 (n=105) | 0.848–0.962 (n=105) | — | — |
| `wrong_auto_rate_upper95` | 0.125 | 0.064 | 0.128 | 0.167 | — | — |
| `ranking.ranked_cases` | 105 | 105 | 105 | 105 | 0 | 0 |
| `ranking.hit@1` | 0.876 | 0.924 | 0.848 | 0.876 | — | — |
| `ranking.hit@3` | 0.914 | 0.943 | 0.905 | 0.905 | — | — |
| `ranking.hit@5` | 0.924 | 0.962 | 0.933 | 0.924 | — | — |
| `ranking.mrr` | 0.899 | 0.938 | 0.885 | 0.897 | — | — |
| `ranking.ndcg@3` | 0.891 | 0.926 | 0.873 | 0.884 | — | — |
| `ranking.type_hit@1` | 0.971 | 0.971 | 0.981 | 0.981 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.057 | 0.038 | 0.048 | 0.057 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.82 | 0.924 | 0.8 | 0.82 | — | — |
| `ranking.dialog_traced` | 105 | 105 | 105 | 105 | 0 | 0 |
| `ranking.mrr_by_step` | 0.899 → 0.921 → 0.933 → 0.933 | 0.938 → 0.957 → 0.962 → 0.962 | 0.885 → 0.935 → 0.952 → 0.952 | 0.897 → 0.926 → 0.943 → 0.943 | — | — |
| `ranking.hit1_by_step` | 0.876 → 0.905 → 0.924 → 0.924 | 0.924 → 0.952 → 0.962 → 0.962 | 0.848 → 0.924 → 0.952 → 0.952 | 0.876 → 0.914 → 0.943 → 0.943 | — | — |
| `ranking.rank_by_step` | 1.63 → 1.07 → 1.02 → 1.02 | 1.08 → 1.01 → 1 → 1 | 1.7 → 1.06 → 1 → 1 | 1.65 → 1.06 → 1 → 1 | — | — |
| `ranking.top1_reached` | 0.924 | 0.962 | 0.952 | 0.943 | — | — |
| `ranking.questions_to_top1_mean` | 0.07 | 0.05 | 0.14 | 0.1 | — | — |
| `ranking.bits_per_question` | 0.551 | 0.557 | 0.666 | 0.629 | — | — |
| `ranking.useless_question_rate` | 0.576 | 0.575 | 0.529 | 0.531 | — | — |
| `ranking.dead_end_rate` | 0.019 | 0.01 | 0.01 | 0.01 | — | — |
| `over_asking` | 0.375 | 0.281 | 0.391 | 0.359 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |

#### typos_human — все кейсы (202)

| метрика | main `33751bb` | Lenaz `f6c5bfc` | aydar `3e1364c` | MVP `86ef95f` | база: baseline:always_clarify | база: baseline:always_not_found |
|---|---|---|---|---|---|---|
| `cases` | 202 | 202 | 202 | 202 | 202 | 202 |
| `status_counts` | clarification: 77, conflict: 2, manual_choice: 5, matched: 67, not_found: 51 | clarification: 77, conflict: 1, manual_choice: 4, matched: 67, not_found: 53 | clarification: 88, conflict: 1, manual_choice: 4, matched: 56, not_found: 53 | clarification: 85, conflict: 1, manual_choice: 4, matched: 59, not_found: 53 | clarification: 202 | not_found: 202 |
| `errors` | 0 | 0 | 0 | 0 | 0 | 0 |
| `auto` | 67 | 67 | 56 | 59 | 0 | 0 |
| `wrong_auto` | 2 | 0 | 2 | 3 | 0 | 0 |
| `wrong_auto_rate` | 0.03 | 0 | 0.036 | 0.051 | — | — |
| `auto_precision` | 0.97 | 1 | 0.964 | 0.949 | — | — |
| `auto_coverage` | 0.332 | 0.332 | 0.277 | 0.292 | 0 | 0 |
| `gold_nonempty` | 171 | 171 | 171 | 171 | 171 | 171 |
| `code_reached@0` | 0.38 | 0.392 | 0.316 | 0.328 | 0 | 0 |
| `dialog_support` | supported | supported | supported | supported | not_supported | not_supported |
| `code_reached@1` | 0.602 | 0.602 | 0.55 | 0.532 | 0 | 0 |
| `code_reached@2` | 0.672 | 0.649 | 0.62 | 0.597 | 0 | 0 |
| `code_reached@3` | 0.731 | 0.69 | 0.672 | 0.649 | 0 | 0 |
| `required_cases` | 59 | 59 | 59 | 59 | 59 | 59 |
| `required_hit` | 0.763 | 0.746 | 0.627 | 0.61 | 0 | 0 |
| `no_code_cases` | 31 | 31 | 31 | 31 | 31 | 31 |
| `no_code_respected` | 1 | 1 | 1 | 1 | 1 | 1 |
| `premature_auto` | 0 | 0 | 0 | 0.05 | 0 | 0 |
| `dialog_wrong_final` | 2 | 0 | 2 | 3 | 0 | 0 |
| `questions_mean` | 0.736 | 0.619 | 0.791 | 0.757 | — | — |
| `latency_ms_p50` | 5.93 | 8.14 | 11 | 6.06 | 0 | 0 |
| `latency_ms_p95` | 25.5 | 26.41 | 37.97 | 20.24 | 0 | 0 |
| `ci95.code_reached@2` | 0.608–0.743 (n=171) | 0.579–0.719 (n=171) | 0.55–0.69 (n=171) | 0.52–0.667 (n=171) | 0–0.018 (n=171) | 0–0.018 (n=171) |
| `ci95.auto_precision` | 0.925–1 (n=67) | 0.955–1 (n=67) | 0.911–1 (n=56) | 0.881–1 (n=59) | — | — |
| `ci95.no_code_respected` | 0.903–1 (n=31) | 0.903–1 (n=31) | 0.903–1 (n=31) | 0.903–1 (n=31) | 0.903–1 (n=31) | 0.903–1 (n=31) |
| `ci95.hit@1` | 0.614–0.754 (n=171) | 0.632–0.76 (n=171) | 0.567–0.708 (n=171) | 0.573–0.714 (n=171) | — | — |
| `ci95.hit@3` | 0.69–0.819 (n=171) | 0.661–0.795 (n=171) | 0.655–0.784 (n=171) | 0.649–0.778 (n=171) | — | — |
| `wrong_auto_rate_upper95` | 0.075 | 0.045 | 0.089 | 0.119 | — | — |
| `ranking.ranked_cases` | 171 | 171 | 171 | 171 | 0 | 0 |
| `ranking.hit@1` | 0.684 | 0.696 | 0.637 | 0.643 | — | — |
| `ranking.hit@3` | 0.754 | 0.731 | 0.719 | 0.713 | — | — |
| `ranking.hit@5` | 0.766 | 0.749 | 0.737 | 0.725 | — | — |
| `ranking.mrr` | 0.72 | 0.716 | 0.679 | 0.678 | — | — |
| `ranking.ndcg@3` | 0.726 | 0.714 | 0.683 | 0.673 | — | — |
| `ranking.type_hit@1` | 0.772 | 0.76 | 0.76 | 0.76 | — | — |
| `ranking.gold_rank_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.gold_not_listed` | 0.228 | 0.246 | 0.257 | 0.269 | — | — |
| `ranking.list_size_median` | 1 | 1 | 1 | 1 | — | — |
| `ranking.list_precision_mean` | 0.848 | 0.871 | 0.816 | 0.822 | — | — |
| `ranking.dialog_traced` | 171 | 171 | 171 | 171 | 0 | 0 |
| `ranking.mrr_by_step` | 0.72 → 0.762 → 0.775 → 0.778 | 0.716 → 0.741 → 0.754 → 0.754 | 0.679 → 0.726 → 0.739 → 0.739 | 0.678 → 0.724 → 0.734 → 0.737 | — | — |
| `ranking.hit1_by_step` | 0.684 → 0.749 → 0.772 → 0.778 | 0.696 → 0.731 → 0.754 → 0.754 | 0.637 → 0.713 → 0.737 → 0.737 | 0.643 → 0.713 → 0.731 → 0.737 | — | — |
| `ranking.rank_by_step` | 1.26 → 1.05 → 1.01 → 1 | 1.24 → 1.05 → 1 → 1 | 1.32 → 1.06 → 1.02 → 1.02 | 1.28 → 1.05 → 1.01 → 1 | — | — |
| `ranking.top1_reached` | 0.778 | 0.754 | 0.737 | 0.737 | — | — |
| `ranking.questions_to_top1_mean` | 0.17 | 0.11 | 0.17 | 0.17 | — | — |
| `ranking.bits_per_question` | 0.776 | 0.732 | 0.725 | 0.563 | — | — |
| `ranking.useless_question_rate` | 0.487 | 0.538 | 0.544 | 0.597 | — | — |
| `ranking.dead_end_rate` | 0.035 | 0.047 | 0.047 | 0.047 | — | — |
| `over_asking` | 0.22 | 0.254 | 0.356 | 0.356 | 1 | 1 |
| `wrong_auto_gold_listed` | 0 | 0 | 0 | 0 | 0 | 0 |
