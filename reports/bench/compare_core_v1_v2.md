## behaviour

| метрика | ktru:core | ktru:core |
| --- | --- | --- |
| pass_rate | 1.0 | 1.0 |
| status_accuracy | 1.0 | 1.0 |
| auto_coverage | 0.333 | 0.333 |
| auto_correct | 6 | 6 |
| auto_incorrect | 0 | 0 |
| auto_precision | 1.0 | 1.0 |
| required_auto_hit | 1.0 | 1.0 |
| forbidden_auto_violations | 0 | 0 |
| forbidden_code_hits | 0 | 0 |
| compatible_recall | 1.0 | 1.0 |
| checks_pass | 1.0 | 1.0 |
| dialog_resolved | 1.0 | 1.0 |
| errors | 0 | 0 |
| latency p50 / p95, мс | 4.69 / 14.01 | 4.61 / 14.48 |

Изменения ktru:core → ktru:core: 0

## manual_dev

| метрика | ktru:core | ktru:core |
| --- | --- | --- |
| pass_rate | 1.0 | 1.0 |
| status_accuracy | 1.0 | 1.0 |
| auto_coverage | 0.607 | 0.607 |
| auto_correct | 17 | 17 |
| auto_incorrect | 0 | 0 |
| auto_precision | 1.0 | 1.0 |
| required_auto_hit | 1.0 | 1.0 |
| forbidden_auto_violations | 0 | 0 |
| forbidden_code_hits | 0 | 0 |
| compatible_recall | 1.0 | 1.0 |
| checks_pass | None | None |
| dialog_resolved | 1.0 | 1.0 |
| errors | 0 | 0 |
| latency p50 / p95, мс | 5.52 / 14.72 | 5.23 / 44.93 |

Изменения ktru:core → ktru:core: 0

## manual_holdout

| метрика | ktru:core | ktru:core |
| --- | --- | --- |
| pass_rate | 1.0 | 1.0 |
| status_accuracy | 1.0 | 1.0 |
| auto_coverage | 0.722 | 0.722 |
| auto_correct | 13 | 13 |
| auto_incorrect | 0 | 0 |
| auto_precision | 1.0 | 1.0 |
| required_auto_hit | 1.0 | 1.0 |
| forbidden_auto_violations | 0 | 0 |
| forbidden_code_hits | 0 | 0 |
| compatible_recall | 1.0 | 1.0 |
| checks_pass | None | None |
| dialog_resolved | 1.0 | 1.0 |
| errors | 0 | 0 |
| latency p50 / p95, мс | 5.09 / 11.05 | 4.75 / 9.5 |

Изменения ktru:core → ktru:core: 0

## synthetic

| метрика | ktru:core | ktru:core |
| --- | --- | --- |
| pass_rate | 0.982 | 1.0 |
| status_accuracy | 0.982 | 1.0 |
| auto_coverage | 0.136 | 0.136 |
| auto_correct | 134 | 134 |
| auto_incorrect | 0 | 0 |
| auto_precision | 1.0 | 1.0 |
| required_auto_hit | None | None |
| forbidden_auto_violations | 6 | 0 |
| forbidden_code_hits | 0 | 0 |
| compatible_recall | 0.981 | 0.997 |
| checks_pass | None | None |
| dialog_resolved | 0.938 | 0.979 |
| errors | 0 | 0 |
| latency p50 / p95, мс | 5.34 / 14.5 | 5.32 / 14.64 |

Изменения ktru:core → ktru:core: 18
- ИСПРАВЛЕНО `S-14.12.30.150-00000008-missing` «перчатки швейные для защиты от внешних воздействий»: matched/14.12.30.150-00000008 → clarification/None
- ИСПРАВЛЕНО `S-14.12.30.150-00000006-base` «перчатки швейные для защиты от внешних воздействий, вид защиты: от пониженных температур»: conflict/None → matched/14.12.30.150-00000006
- ИСПРАВЛЕНО `S-14.12.30.150-00000006-typo` «перачтки швейные для защиты от внешних воздействий, вид защиты: от пониженных температур»: conflict/None → matched/14.12.30.150-00000006
- ИСПРАВЛЕНО `S-14.12.30.150-00000006-missing` «перчатки швейные для защиты от внешних воздействий»: matched/14.12.30.150-00000008 → clarification/None
- ИСПРАВЛЕНО `S-14.12.30.160-00000599-base` «перчатки из полимерных материалов для защиты от внешних воздействий, вид защиты: от радиоактивных загрязнений»: conflict/None → matched/14.12.30.160-00000599
- ИСПРАВЛЕНО `S-14.12.30.160-00000599-typo` «перчтаки из полимерных материалов для защиты от внешних воздействий, вид защиты: от радиоактивных загрязнений»: conflict/None → matched/14.12.30.160-00000599
- ИСПРАВЛЕНО `S-14.12.30.160-00000599-missing` «перчатки из полимерных материалов для защиты от внешних воздействий»: matched/14.12.30.160-00000601 → clarification/None
- ИСПРАВЛЕНО `S-14.12.30.160-00000601-missing` «перчатки из полимерных материалов для защиты от внешних воздействий»: matched/14.12.30.160-00000601 → clarification/None
- ИСПРАВЛЕНО `S-31.09.10.000-00000004-base` «стол администратора, тип каркаса: металлический, вид товара: секция стола, количество выдвижных ящиков 4 шт»: conflict/None → clarification/None
- ИСПРАВЛЕНО `S-31.09.10.000-00000004-perm` «стол администратора, количество выдвижных ящиков 4 шт, вид товара: секция стола, тип каркаса: металлический»: conflict/None → clarification/None
- ИСПРАВЛЕНО `S-14.12.30.150-00000002-base` «перчатки трикотажные для защиты от внешних воздействий, вид защиты: от повышенных температур»: conflict/None → matched/14.12.30.150-00000002
- ИСПРАВЛЕНО `S-14.12.30.150-00000002-typo` «перчтаки трикотажные для защиты от внешних воздействий, вид защиты: от повышенных температур»: conflict/None → matched/14.12.30.150-00000002
- ИСПРАВЛЕНО `S-14.12.30.150-00000002-missing` «перчатки трикотажные для защиты от внешних воздействий»: matched/14.12.30.150-00000003 → clarification/None
- ИСПРАВЛЕНО `S-14.12.30.150-00000003-missing` «перчатки трикотажные для защиты от внешних воздействий»: matched/14.12.30.150-00000003 → clarification/None
- ИСПРАВЛЕНО `S-31.01.11.121-00000005-base` «шкаф хозяйственный металлический, вид товара: секция шкафа»: conflict/None → clarification/None
- ИСПРАВЛЕНО `S-31.01.12.110-00000004-base` «стол для переговоров, вид товара: секция стола для переговоров»: conflict/None → clarification/None
- ИСПРАВЛЕНО `S-31.01.11.121-00000001-base` «шкаф для одежды металлический, вид товара: секция шкафа, глубина 399 мм, длина полки 299 мм»: conflict/None → clarification/None
- ИСПРАВЛЕНО `S-31.01.11.121-00000001-perm` «шкаф для одежды металлический, длина полки 299 мм, глубина 399 мм, вид товара: секция шкафа»: conflict/None → clarification/None

