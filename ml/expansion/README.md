# Расширение данных и проверка моделей

Результат: [выводы](../../reports/expansion/conclusions.md), [исполненный notebook](../../notebooks/03_data_expansion.ipynb), [HTML](../../reports/expansion/data_expansion.html). До экспериментов зафиксирован [протокол](protocol.md).

## Воспроизведение

Из корня проекта, Python 3.12. Исходные MARIDA EDA/модель должны быть подготовлены по `ml/marida/README.md`, а CV membership — по `ml/eda/README.md`. EMBLAS Excel описан в `docs/emblas-coordinate-search.md`.

```bash
uv venv ml/.venv --python 3.12
uv pip install --python ml/.venv/bin/python -r ml/expansion/requirements.lock.txt
uv pip install --python ml/.venv/bin/python -e './backend[dev]'
ml/.venv/bin/python scripts/data/fetch.py download mados --yes
ml/.venv/bin/python scripts/data/fetch.py unpack mados
ml/.venv/bin/python scripts/data/fetch.py download plp2019
ml/.venv/bin/python scripts/data/fetch.py unpack plp2019
ml/.venv/bin/python ml/expansion/field_data.py
ml/.venv/bin/python ml/expansion/weather.py
ml/.venv/bin/python ml/expansion/mados.py
ml/.venv/bin/python ml/expansion/report.py
ml/.venv/bin/python -m pytest -q ml/expansion/test_contracts.py
```

Проверка backend: из `backend/` выполнить `../ml/.venv/bin/python -m pytest -q`.

`mados.py` кеширует извлечённые пиксели в `data/processed/expansion/mados_pixels.npz`; при повторном запуске переобучает фиксированные модели. Если изменены входные TIFF или правила извлечения, удалите только этот воспроизводимый кеш, чтобы повторить сканирование. `weather.py` сохраняет ответы ERA5 и URL запросов; повтор использует эти snapshots. `report.py` исполняет все аналитические ячейки, независимо пересчитывает метрики из сохранённых scores и создаёт notebook/HTML/PNG. Он не переобучает модели.

## Артефакты

- `reports/expansion/tables/emblas_events_pending.csv`: 302 сессии; площади, числа предметов, нули, source row/SHA-256, время как опубликовано; координаты пустые, T3 eligibility закрыта.
- `plp2019_pixel_cover.csv`: 65 точек; 63 допустимых пространственных сопоставления, исходные material cover и NetCDF paths.
- `mados_inventory.csv`, `mados_split_summary.csv`: 2803 патча и разделение сцен; исходные class counts, контроль известных дублей.
- `detector_*.csv`: пороги validation, метрики, ошибки по классам, bootstrap по сценам/группам.
- `era5_event_context.csv`, `weather_*.csv`: context предыдущего дня для 74 событий и paired ablation на прежних folds.
- `data/processed/expansion/`: два RF joblib, metadata, 11-канальные размеченные пиксели и предсказания с полной точностью scores. Эти большие данные исключены из Git.
- `run_manifest.json`, `tables/artifact_hashes.csv`: контрольные суммы входов, программ и результатов; архивы проверены по опубликованным MD5.

Модели — исследовательские артефакты. Не подключены к `Detector`/`ConcentrationModel`: перенос на L2A, концентрацию items/km² и российские моря не подтверждён. Метаданных дат/координат MADOS недостаточно для полного совместного контроля утечки MARIDA/MADOS. Результаты нельзя объявлять независимым внешним benchmark.

## Источники

MADOS (Kikaki et al., 2024), [Zenodo 10664073](https://doi.org/10.5281/zenodo.10664073), CC BY 4.0. PLP2019 (University of the Aegean), [Zenodo 3752719](https://doi.org/10.5281/zenodo.3752719), CC BY 4.0. EMBLAS: González-Fernández et al. (2022), [DOI](https://doi.org/10.1016/j.envpol.2022.119816), Table S2; перед публикацией производной базы уточнить применимые условия повторного использования supplementary data. Погода: ERA5/Copernicus, обработка и API [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api), атрибуция Open-Meteo и Copernicus Climate Change Service; данные Open-Meteo CC BY 4.0. Бесплатный endpoint использован для исследования, не подключён к production.
