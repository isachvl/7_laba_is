# ЛР7 — трейсинг и регрессионный гейт

Для показа готовых измерений модель и GPU не нужны. Нужен Python 3.12. В PowerShell из папки проекта:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe prepare_laptop.py
Start-Process .\report.pdf
Start-Process .\dashboard.local.html
.\.venv\Scripts\mlflow.exe ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5006
```

Откройте http://127.0.0.1:5006, эксперимент lr7. Во вкладке Traces находятся настоящие деревья спанов: AGENT → CHAT_MODEL / TOOL. Включите столбцы/фильтры тегов task, evaluation, run, utility. Если список пуст, сбросьте фильтр времени: сохранены исходные даты измерений.

В Model training четыре серии: base, aa, candidate, fix. Четыре метрики: success — доля успешных эпизодов; median_total_tokens — медиана суммы входных и выходных токенов; median_seconds — медиана времени эпизода; protected_lost — число потерянных защищаемых задач. Статус гейта хранится тегом gate_status. Два общих изображения лежат в запуске base → Artifacts → analysis, отчёт — в report.

prepare_laptop.py восстанавливает 370 измеренных трейсов из native_traces с настоящими родительскими связями, содержимым, токенами, статусами и длительностями. Импорт может занять несколько минут. При импорте технические ID меняются; исходные сохранены в origin_trace_id и origin_span_id. Файл .laptop/trace_map.json сопоставляет ID. Локальные HTML-дашборды получают обновлённые ссылки. Повторная подготовка использует сохранённые трейсы и не запускает модель.

Проверить сохранённые результаты:

```powershell
.\.venv\Scripts\python.exe verify_results.py
```

Запустить гейт без модели:

```powershell
.\.venv\Scripts\python.exe gate.py eval/base/summary.json eval/aa/summary.json --report aa_report.html
.\.venv\Scripts\python.exe gate.py eval/base/summary.json eval/candidate/summary.json --report candidate_report.html
.\.venv\Scripts\python.exe gate.py eval/base/summary.json eval/fix/summary.json --report fix_report.html
```

Коды завершения: PASS/REVIEW — 0; FAIL — 1; ERROR — 2. REVIEW требует ручного разбора. Ненулевой код для отвергнутого кандидата ожидаем и означает, что гейт выполнил свою работу.

Проверки без генерации:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ci.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Настоящие GitHub Actions настроены в .github/workflows/regression.yml: установка зависимостей, эти тесты и gate.py. Генерация в CI не выполняется. При ручном workflow_dispatch можно выбрать aa, candidate или fix. Локальные журналы эквивалентных команд находятся в analysis/ci_logs; они не выдаются за облачные запуски GitHub.

Файлы: report.pdf — отчёт на 4 страницы; eval/*/summary.json — сводки серий; versions — полные манифесты; traces — пошаговые журналы агента; native_traces — экспортированные настоящие MLflow Traces; analysis/dashboards — HTML-дашборды; analysis/divergence_candidates.json и reviews.json — первые расхождения и их разбор; hypothesis.md — прогноз и пороги до измерений; frozen.json — хеши; checks.txt — исходные тесты.

Измерено 380 эпизодов: по 90 для базы, A/A, обрезки и исправления, плюс 20 парных отладочных. Контроль с фиксированными сохранёнными ответами отдельно измеряет обвязку без генерации и не подменяет свежие прогоны. Предварительная техническая попытка с несовместимым типом фиксированной даты сохранена локально в diagnostics/protocol_v1; после исправления все сравниваемые условия измерены заново. Реальные таймеры спанов не замораживались.

Для новых измерений используйте отдельную копию и сохраните эти результаты. Установите requirements.txt. Выполните download_runtime.py и start_server.py, затем Git-коммит и freeze.py. Команды оценки: eval.py --version base --runs 3, затем aa, candidate и fix. После завершения всех оценок выполните finalize_exports.py для экспорта завершённых деревьев из базы после асинхронной записи; парный опыт — eval.py --phase overhead. Нужна совместимая NVIDIA GPU. Пороговые правила до измерений: потеря защищаемой задачи при <2 успехах из 3; REVIEW при росте медианы суммы токенов/времени >25%, потере в среднем >=1 остальных задач или <5 защищаемых. Пороги не подбираются по результатам.
