# MARIDA: EDA и первый детектор

[Выполненный notebook](../../notebooks/02_marida_eda.ipynb),
[HTML](../../reports/marida/marida_eda.html),
[выводы](../../reports/marida/conclusions.md).

## Получение данных

Источник: [MARIDA v1](https://zenodo.org/records/5151941), лицензия CC BY 4.0.
Авторы: Kikaki, Kakogeorgiou, Mikeli, Raitsos, Karantzalos.
Статья: DOI [10.1371/journal.pone.0262247](https://doi.org/10.1371/journal.pone.0262247).
Порядок каналов и классов сверяется с [авторским кодом](https://github.com/marine-debris/marine-debris.github.io).

Из корня репозитория:

```bash
uv venv ml/.venv --python 3.12
uv pip sync --python ml/.venv/bin/python ml/marida/requirements.lock.txt
ml/.venv/bin/python scripts/data/fetch.py download marida
ml/.venv/bin/python scripts/data/fetch.py verify marida
ml/.venv/bin/python scripts/data/fetch.py unpack marida
ml/.venv/bin/python ml/marida/run.py
ml/.venv/bin/python ml/marida/verify.py
```

Архив — 1,165 GB, распакованные файлы — около 4,7 GB. MD5 архива:
`9bf32266f6e3711c9dfa3699b856c76f`. Загрузчик поддерживает докачку. Ноутбук требует
локальные файлы и выполняется без сети; GPU не нужен, RF использует 4 CPU-потока.
Промежуточные массивы занимают дополнительное место в `data/processed/`.
`verify.py` без переобучения пересчитывает метрики из сохранённых ответов, сверяет
полные маски с пиксельными предсказаниями и проверяет разбиения/контрольные суммы.
Не запускайте `uv venv` повторно поверх работающего окружения: для существующего
окружения достаточно `uv pip sync`.

`marida_eda.py` — исходник notebook в формате `# %%`; менять анализ следует в нём.
`run.py` пересоздаёт notebook, исполняет все ячейки, сохраняет outputs и HTML.
При ошибке сохраняется notebook для диагностики, HTML не обновляется.

## Что проверяется

- Все изображения, class/confidence-маски, сетки, CRS, конечность значений и словари.
- Дисбаланс классов, полнота аннотаций, уверенность, распределения спектров на train.
- Исходные split-файлы, общие сцены, точные дубли и пространственно-временная близость.
- Новый строгий split без разрыва связанных компонент, с сохранением исходного test.
- Два фиксированных baseline: порог B08 и Random Forest по 11 каналам.
- Порог только по validation; test precision, recall, F1, IoU, average precision,
  разбор сложного фона и интервалы bootstrap целых групп.
- Полные геопривязанные маски и карты ошибок для трёх контрольных случаев.

Правило строгого split зафиксировано до обучения в `config.toml`: общая сцена,
точный дубль, центры ≤25 км/≤3 суток или ≤100 км в один день. Связанные компоненты
переносятся в часть с приоритетом test > val > train. Значения классов не участвуют
в переносах. Это новый эксперимент; его метрики не сравниваются напрямую с
авторским benchmark. Общие регионы в разные даты остаются: перенос на новые моря
не проверен.

## Артефакты

- `reports/marida/tables/split_membership.csv` — patch/scene/group IDs и обе версии split.
- `split_integrity.csv` — пересечения частей до и после группировки.
- `detector_metrics.csv`, `thresholds.csv`, `errors_by_reference_class.csv` — метрики и ошибки.
- `group_bootstrap_intervals.csv` — интервалы по группам, без переобучения модели.
- `input_hashes.csv`, `run_info.json` — контрольные суммы, окружение и параметры.
- `data/processed/marida/annotated_pixels.npz` — признаки, исходный класс, confidence,
  номер патча и пиксельные координаты всех пригодных аннотаций.
- `data/processed/marida_baseline/spectral_forest.joblib` — обученная модель.
- `model_metadata.json` — радиометрический контракт, конфигурация и пороги.
- `heldout_predictions.npz` — validation/test ответы, scores и предсказания с координатами.
- `examples/*_mask.tif`, `examples/*_score.tif` — полные GeoTIFF-предсказания.

Изображения, массивы и веса находятся в игнорируемом Git каталоге `data/`.
Notebook, отчёт, код и таблицы остаются в репозитории. Полная команда выше
восстанавливает большие артефакты; файл модели требует доверенного локального происхождения.

## Применение к патчу

```bash
ml/.venv/bin/python ml/marida/predict.py \
  data/external/marida/patches/S2_1-12-19_48MYU/S2_1-12-19_48MYU_0.tif \
  data/processed/marida_baseline/example
```

Вход — 11 каналов MARIDA **ACOLITE Rayleigh reflectance** в порядке
B01, B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12.
Деление на 10000 к этим float-растрам не применяется.
Выход mask: 0 — отрицательное предсказание, 1 — вероятный marine debris,
255 — технически непригодный пиксель. Score не калиброванная вероятность.
Class=0 эталонной маски — ignore; он никогда не используется как отрицательная метка.

## Ограничения

MARIDA имеет неполную разметку: метрики относятся только к аннотированным пикселям.
Положительные срабатывания вне аннотаций не являются автоматически FP.
Перенос ACOLITE → текущий Sentinel-2 L2A Littora требует отдельной проверки.
Модель не подключается к backend автоматически. Концентрацию в шт./км² она не оценивает.
После использования ошибок текущего test для новых решений нужен дополнительный
внешний holdout; существующий test становится development benchmark.
