# EDA и проверка прироста скора

Из корня проекта, с существующим окружением ml/.venv и артефактами marida, expansion, validation_bridge:

```sh
ml/.venv/bin/python ml/score_check/run.py
ml/.venv/bin/python ml/score_check/report.py
ml/.venv/bin/python -m pytest -q ml/score_check/test_score_check.py
```

run.py выполняет новый inference трёх сохранённых RF на 642168 прежних test/development пикселях и 120 размеченных пикселях двух пар L2A/rhorc. Тестовая пара (114) и обучающая пара (6) не объединяются. Затем выполняется EDA новых полевых таблиц и 12 неразмеченных снимков. report.py строит 6 фигур, исполняет notebook 05 и сохраняет HTML. Большие полные scores находятся в data/processed/score_check, исходные веса не перезаписываются.

Пороги заранее зафиксированы в protocol.md. Обучения на новых данных нет: их метки не готовы. Нельзя выдавать старый эффект MADOS за новый эффект DOORS или спутниковых кропов. Контроль общего порога — диагностика, не перенастройка модели. Неизвестные пиксели holdout не превращаются в negative, а предсказания на этих сценах не вычисляются.

Результаты: reports/score_check/conclusions.md, eda_score_check.html, tables/, run_manifest.json; notebooks/05_eda_score_check.ipynb. Для зависимостей используется существующий lock ml/validation_bridge/requirements.lock.txt. Полный прогон локальный, сетевые запросы не нужны. Код сохраняет SHA256 защищённых входов до/после, свежие scores сверяются с прежними с atol=1e-12. После завершения реального review протокол потребуется пересмотреть — нынешний прогон намеренно требует пустых исходных labels.
