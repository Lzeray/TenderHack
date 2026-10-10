# Отчёт: ktru:core

Дата: 2026-10-10 14:57; машина: Linux-7.0.0-34-generic-x86_64-with-glibc2.39

| метрика | behaviour | manual_dev | manual_holdout | synthetic |
| --- | --- | --- | --- | --- |
| cases | 18 | 28 | 18 | 984 |
| pass_rate | 1.0 | 1.0 | 1.0 | 1.0 |
| status_accuracy | 1.0 | 1.0 | 1.0 | 1.0 |
| auto_coverage | 0.333 | 0.607 | 0.722 | 0.142 |
| auto_correct | 6 | 17 | 13 | 140 |
| auto_incorrect | 0 | 0 | 0 | 0 |
| auto_precision | 1.0 | 1.0 | 1.0 | 1.0 |
| error_upper95 | 0.5 | 0.176 | 0.231 | 0.021 |
| required_auto_hit | 1.0 | 1.0 | 1.0 | None |
| forbidden_auto_violations | 0 | 0 | 0 | 0 |
| forbidden_code_hits | 0 | 0 | 0 | 0 |
| compatible_recall | 1.0 | 1.0 | 1.0 | 0.999 |
| checks_pass | 1.0 | None | None | None |
| dialog_resolved | 1.0 | 1.0 | 1.0 | 0.986 |
| dialog_steps_mean | 1.83 | 1.8 | 1.5 | 2.28 |
| determinism | None | None | None | None |
| errors | 0 | 0 | 0 | 0 |
| latency p50 / p95, мс | 4.82 / 17.46 | 3.99 / 17.04 | 4.52 / 11.42 | 3.83 / 15.49 |

Ранжирование и диалог (hit@k — эталон в первых k строках до вопросов; *_by_step — после 0, 1, 2… ответов; type_hit@1 — первая строка того же ОКПД2):

| метрика | behaviour | manual_dev | manual_holdout | synthetic |
| --- | --- | --- | --- | --- |
| hit@1 | 1.0 | 1.0 | 1.0 | 0.951 |
| hit@3 | 1.0 | 1.0 | 1.0 | 0.982 |
| hit@5 | 1.0 | 1.0 | 1.0 | 0.99 |
| mrr | 1.0 | 1.0 | 1.0 | 0.968 |
| ndcg@3 | 1.0 | 1.0 | 1.0 | 0.965 |
| type_hit@1 | 1.0 | 1.0 | 1.0 | 0.997 |
| gold_rank_median | 1.0 | 1.0 | 1 | 1.0 |
| gold_not_listed | 0.0 | 0.0 | 0.0 | 0.001 |
| list_size_median | 1.0 | 1.0 | 1 | 2 |
| list_precision_mean | 1.0 | 0.977 | 1.0 | 0.941 |
| top1_reached | 1.0 | 1.0 | 1.0 | 0.999 |
| questions_to_top1_mean | 0 | 0 | 0 | 0.05 |
| rank_by_step | [1, 1, 1, 1, 1, 1, 1] | [1, 1, 1, 1, 1, 1, 1] | [1, 1, 1, 1, 1, 1, 1] | [1.13, 1.0, 1, 1, 1, 1, 1] |
| hit1_by_step | [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0] | [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0] | [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0] | [0.951, 0.995, 0.999, 0.999, 0.999, 0.999, 0.999] |
| mrr_by_step | [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0] | [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0] | [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0] | [0.968, 0.997, 0.999, 0.999, 0.999, 0.999, 0.999] |
| bits_per_question | 0.0 | 0.111 | 0.0 | 0.458 |
| useless_question_rate | 1.0 | 0.889 | 1.0 | 0.671 |
| dead_end_rate | 0.0 | 0.0 | 0.0 | 0.0 |
| over_asking | 0.0 | 0.0 | 0.0 | None |

Непройденные кейсы:

