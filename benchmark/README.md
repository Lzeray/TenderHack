# Общий набор тестов подбора КТРУ

Набор не зависит от реализации: любое решение подключается адаптером (`adapters/base.py`) и получает
одинаковые метрики по каждому набору кейсов. Отчёты двух решений сравниваются `benchmark.compare`.

```bash
# наше решение: ядро без моделей, в процессе (нужна data/ktru.sqlite)
python -m benchmark.run --adapter ktru:core --suites all --dialog --out reports/bench/core.json
# наше решение с моделями (нужны Ollama и модели, см. корневой README)
python -m benchmark.run --adapter ktru:core_sem_b --suites all --dialog --out reports/bench/core_sem_b.json
# запущенный сервер (любой конфигурации)
python -m benchmark.run --adapter ktru_http:http://127.0.0.1:8000 --suites behaviour --out reports/bench/http.json
# чужое решение: скопируйте adapters/template.py и реализуйте predict()
python -m benchmark.run --adapter benchmark.adapters.template:MyAdapter --suites all --out reports/bench/my.json
# сравнение
python -m benchmark.compare reports/bench/core.json reports/bench/core_sem_b.json --out reports/bench/compare.md
```

Каждый прогон пишет `*.json` (все кейсы) и `*.md` (таблица метрик и непройденные кейсы).
Флаги: `--split dev|test` — только часть кейсов; `--repeat 2` — проверка детерминизма; `--dialog` — симуляция
уточнений (только для адаптеров с методом `dialog`).

## Наборы (`suites/`)

| Набор | Кейсов | Что проверяет | Происхождение |
| --- | --- | --- | --- |
| `behaviour` | 18 | обязательное поведение из плана (п. 10.1–10.2): единицы, В≠Вт, отрицания, «45 м», противоречия, инъекция, перестановка, сужение, опечатки | вручную, по реальному снимку `nsiKTRUNew_all_actual_20261003020003` |
| `manual_dev` | 28 | ручная разметка разработки | `eval/cases.jsonl` |
| `manual_holdout` | 18 | отложенный набор, размечен до первого прогона | `eval/holdout.jsonl` (не править под систему) |
| `synthetic` | 984 | синтетика из каталога: базовый запрос, опечатка, перестановка, пропуск, конфликт, вне области | `eval/synth.py`; эталон проверен по всей области наименования |

Синтетика — не независимая оценка живых запросов: формулировки близки к названиям КТРУ.
Разбиение `split` синтетики — по наименованию позиции (варианты одного примера в одном split).

## Формат кейса

```json
{"id": "B05-negation", "suite": "behaviour", "split": "test", "text": "стул … без мягкого сиденья …",
 "acceptable_codes": ["31.01.11.150-00000001"], "auto": "required", "expected_status": ["matched"],
 "forbidden_codes": ["31.01.11.150-00000003"], "checks": [{"type": "no_feature", "property": "мягкого сид", "value": "Да"}],
 "verified": "основание эталона", "plan": "пункт плана"}
```

- `acceptable_codes` — все коды, которые эксперт считает верными;
- `auto`: `required` — нужен автоматический верный код; `allowed` — код можно выдать, но только верный;
  `forbidden` — автоматический код недопустим (нужно уточнение, противоречие, вне области);
- `expected_status` — допустимые статусы (`matched`, `clarification`, `conflict`, `not_found`, `manual_choice`);
  пустой список — статус не проверяется;
- `forbidden_codes` — коды, выдача которых — ошибка (шаблоны, противоположные позиции, код из инъекции);
- `checks` — дополнительные проверки:
  `same_as` (тот же статус и код, что для другого текста), `subset_of` (совместимые ⊆ совместимых для другого текста),
  `warning` (есть предупреждение), `feature` / `no_feature` (признак со свойством, содержащим подстроку,
  и значением/единицей есть / отсутствует). Проверка, для которой решение не отдаёт данных, — `not_supported`.

Кейс пройден (`pass`), если выполнено правило `auto`, статус допустим, запрещённые коды не выданы
и все поддерживаемые проверки прошли.

## Метрики (по каждому набору)

| Метрика | Смысл |
| --- | --- |
| `pass_rate` | доля пройденных кейсов |
| `status_accuracy` | доля кейсов с допустимым статусом (где он задан) |
| `auto_coverage` | доля автоматических кодов (`matched`) |
| `auto_correct` / `auto_incorrect` | автоматических кодов из `acceptable_codes` / вне их — **главная метрика безопасности** |
| `auto_precision` | верные / все автоматические |
| `error_upper95` | при 0 ошибочных: 3/n — верхняя 95%-граница доли ошибок («правило трёх») |
| `required_auto_hit` | доля кейсов `auto=required`, где выдан верный код |
| `forbidden_auto_violations` | кейсов `auto=forbidden`, где код всё же выдан |
| `forbidden_code_hits` | выдан код из `forbidden_codes` |
| `compatible_recall` | эталон среди совместимых кандидатов (если решение их отдаёт) |
| `checks_pass`, `checks_by_type` | доля пройденных доп. проверок, разбивка по типам |
| `dialog_resolved`, `dialog_steps_mean` | доля дошедших до верного кода уточнениями и среднее число шагов |
| `latency_ms` | p50 / p95 / max / mean полного вызова `predict` |
| `determinism` | доля совпавших ответов при `--repeat ≥ 2` |
| `errors` | исключения решения |

Порядок сравнения решений: сначала безопасность (`auto_incorrect`, `forbidden_*` — меньше), затем полезность
(`pass_rate`, `required_auto_hit`, `auto_coverage`), затем диалог и задержка. Единого «балла» нет намеренно:
доля автоматических решений без доли ошибок ничего не говорит.

## Как добавить кейс

1. Найдите позиции в каталоге (`tools/sql.py`, `tools/family.py`) и проверьте **все** позиции области.
2. Допишите строку в `suites/behaviour.jsonl` (или в `eval/*.jsonl` и пересоберите `python -m benchmark.build_suites`).
3. Основание эталона — в `verified`; спорные кейсы перепроверяет второй участник.
