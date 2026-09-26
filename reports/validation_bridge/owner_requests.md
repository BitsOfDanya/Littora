# Запросы владельцам данных — подготовлены, не отправлены

Дата проверки: 26.09.2026. Для геометрии требуется связь с исходным ID наблюдения, а не координаты соседней CTD-станции.

## DOORS, июнь 2024: 33 визуальные трансекты

Получатель: Violeta Slabakova, `v.slabakova@io-bas.bg`. Адрес опубликован в [официальном списке Argo](https://argo.ucsd.edu/organization/ast-and-ast-executive-members/); она указана сборщиком данных в Zenodo. DOI [15129753](https://zenodo.org/records/15129753) и [15172377](https://zenodo.org/records/15172377) содержат одинаковые 33 записи, но являются отдельными Zenodo records.

Subject: DOORS cruise 3 floating macrolitter T1–T33: UTC and transect geometry

Dear Dr Slabakova,

We are preparing a reproducible Black Sea satellite validation dataset using the ship-based visual floating macrolitter observations from DOORS cruise 3 (June 2024). We have downloaded the public tables under DOI 10.5281/zenodo.15129753 and DOI 10.5281/zenodo.15172377. Both contain the same T1–T33 records with calendar dates, positions and densities.

Could you share an export linked to these exact transect IDs containing UTC start/end times, WGS84 start/end coordinates or timestamped GPS tracks, surveyed strip width, transect length and surveyed area, and observed item counts including zero-count transects? Please also confirm whether the published coordinates represent transect midpoints, the minimum detectable size, observer height, sea state, any effort/detection corrections, and the reuse licence.

For T33, both public files give latitude 29.21475 and longitude 43.35643. Reversing them yields a Black Sea location (43.35643 N, 29.21475 E); could you confirm this correction?

We also found the TriOS/AOP water-optics measurements from the same cruise. We will keep them separate unless you can provide an explicit link to the litter observation intervals. CSV, GeoJSON or an original JRC/Floating Litter Monitoring export would be suitable.

Thank you.

## EMBLAS: 302 сессии 2017/2019

Получатели и готовый текст: [существующий аудит EMBLAS](../../docs/emblas-coordinate-search.md#самый-прямой-путь-к-недостающему-экспорту). Первый контакт — Daniel González-Fernández, `daniel.gonzalez@uca.es`; резервный оператор JRC — `JRC-FloatingLitterMonitoring@ec.europa.eu`.

Приложить `reports/expansion/tables/emblas_events_pending.csv`. Запросить координаты/треки и UTC через Monitoring Session ID. Площадь, ширина и числитель уже опубликованы; сохранить все 40 нулевых сессий. Российские шесть строк Table S1 относятся к программам/экспедициям, не к шести сессиям.

## Дополнительный резерв: июль 2024, 8 трансект Румынии

[Castro-Rosero et al., 2025, DOI 10.1016/j.scitotenv.2025.181035](https://upcommons.upc.edu/entities/publication/996e8232-bed7-4a0b-a5e9-2bd9ec4c01dc), corresponding author: `lcastrro22@alumnes.ub.edu`, адрес в PDF, стр. 1. Это другая кампания, не июньские T1–T33.

Subject: Georeferenced July 2024 FMML transects T1–T8, STOTEN 181035

Dear Dr Castro-Rosero,

We are preparing a satellite validation dataset for floating marine macrolitter in the Black Sea. We have Table 1 of your paper (DOI 10.1016/j.scitotenv.2025.181035), including the eight July 2024 transect IDs, station pairs, dates, lengths and observed areas. Could you share the corresponding WGS84 endpoints/midpoints, UTC observation start/end times, item counts and densities by transect, and GPS tracks where available? We would also appreciate confirmation of the effective total strip width (two non-overlapping 7 m observer strips) and the reuse licence for the observation data. We will keep these observations separate from the June 2024 DOORS cruise 3 records.

Thank you.
