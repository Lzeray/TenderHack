# Отчёт: ktru:core

Дата: 2026-10-10 10:33; машина: macOS-27.0.1-arm64-arm-64bit-Mach-O

| метрика | behaviour | manual_dev | manual_holdout | synthetic |
| --- | --- | --- | --- | --- |
| cases | 18 | 28 | 18 | 984 |
| pass_rate | 1.0 | 0.857 | 1.0 | 1.0 |
| status_accuracy | 1.0 | 0.857 | 1.0 | 1.0 |
| auto_coverage | 0.333 | 0.464 | 0.667 | 0.138 |
| auto_correct | 6 | 13 | 12 | 136 |
| auto_incorrect | 0 | 0 | 0 | 0 |
| auto_precision | 1.0 | 1.0 | 1.0 | 1.0 |
| error_upper95 | 0.5 | 0.231 | 0.25 | 0.022 |
| required_auto_hit | 1.0 | 0.75 | 1.0 | None |
| forbidden_auto_violations | 0 | 0 | 0 | 0 |
| forbidden_code_hits | 0 | 0 | 0 | 0 |
| compatible_recall | 1.0 | 0.955 | 1.0 | 0.997 |
| checks_pass | 1.0 | None | None | None |
| dialog_resolved | 1.0 | 0.6 | 0.5 | 0.786 |
| dialog_steps_mean | 2.67 | 1 | 1 | 2.05 |
| determinism | 1.0 | 1.0 | 1.0 | 1.0 |
| errors | 0 | 0 | 0 | 0 |
| latency p50 / p95, мс | 31.17 / 130.34 | 48.98 / 382.81 | 40.6 / 214.89 | 33.89 / 190.43 |

Непройденные кейсы:

- `manual_dev/T05` clarification  — «шуруповерт аккумуляторный» (ожидалось: auto=required, коды 28.24.11.000-00000030; проверки: {})
- `manual_dev/T09` clarification  — «молоток слесарный масса головки 0,5 кг» (ожидалось: auto=required, коды 25.73.30.141-00000012; проверки: {})
- `manual_dev/F05` not_found  — «табуретка на металлическом каркасе с мягким сиденьем, ножки, обивка экокожа» (ожидалось: auto=required, коды 31.09.10.000-00000018; проверки: {})
- `manual_dev/C05` clarification  — «брюки женские трикотажные» (ожидалось: auto=required, коды 14.13.12.140-00000001; проверки: {})
