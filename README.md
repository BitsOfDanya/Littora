# Littora

Littora — рабочее пространство для спутникового мониторинга макропластика в морских акваториях. Проект команды «5 bit» для финала КосмоХакатона, кейс «Детектирование и оценка концентрации макропластика в морских акваториях».

По снимкам Sentinel-2 система будет:

- находить вероятные скопления плавающего мусора;
- оценивать степень загрязнения;
- показывать, как пятна меняются от снимка к снимку и куда их сносит течение;
- подсказывать, какие участки стоит обследовать с судна или беспилотника.

## Статус

Готова основа проекта: интерфейс, сервер и данные. Моделей пока нет.

- **Интерфейс.** Экран входа и рабочее пространство на одной карте. Пять режимов: Мониторинг, Динамика, Прогноз, Обследование, Модели.
- **Сервер.** FastAPI с `/api/v1/health` и `/api/v1/meta`, единым форматом ошибок и CORS.
- **Данные.**
  - Каталог из 49 внешних источников с загрузчиком.
  - 33 района интереса в морях России со снимками Sentinel-2.
  - Структура под официальный датасет кейса.
- **Запуск.** Docker Compose поднимает всё целиком.

Все панели анализа сейчас показывают демонстрационные данные с пометкой «ДЕМО». Клавиша `D` их отключает, и тогда видно честное состояние «не подключено».

Пока не реализовано:

- детекция, сегментация и оценка концентрации;
- каталог реальных сцен в интерфейсе: под данными лежит годовая мозаика EOX;
- расчёт дрейфа и ранжирование участков для обследования;
- хранилище и тайловый сервер для растров.

## Архитектура

```
frontend/     Next.js 16, TypeScript, Tailwind CSS 4, MapLibre GL 6, deck.gl 9
backend/      FastAPI, pydantic-settings, pytest, ruff
ml/           модели, пока пусто
data/         данные; в git только каталог источников, районы и манифесты
scripts/data/ загрузка и подготовка данных
compose.yaml  frontend и backend в контейнерах
```

Frontend:

- Карта одна на всё приложение. Её не пересоздают ни при смене режима, ни при входе с экрана входа.
- Режимы — это страницы Next.js. Каждая добавляет свои панели в общую оболочку и свои слои deck.gl на карту.
- Интерфейс получает данные только через хуки `src/data/*`. Каждый ответ помечен источником: `api`, `demo` или `none`.
- Демонстрационные данные лежат отдельно в `src/demo`. Импортировать их откуда-то ещё запрещает eslint.

Backend:

- Приложение собирается в `create_app()`.
- Настройки читаются из переменных `LITTORA_*`.
- Ошибки возвращаются в одном формате `{"error": {...}}` с `X-Request-ID`.
- Реестр возможностей платформы отдаётся в `/api/v1/meta`. Когда возможность готова, её статус меняется с `planned` на `available`, и интерфейс сам перестаёт показывать «не подключено».

## Запуск в Docker

Нужен Docker с Compose v2.

```bash
docker compose up -d --build
```

- http://localhost:3000 — приложение;
- http://localhost:8000/api/docs — документация API.

В контейнере фронтенд проксирует `/api/*` в сервис `backend`, поэтому CORS настраивать не нужно. Порты меняются в `.env` через `LITTORA_FRONTEND_PORT` и `LITTORA_BACKEND_PORT`. После изменения `NEXT_PUBLIC_*` нужна пересборка с `--build`.

```bash
docker compose ps
```

```bash
docker compose down
```

## Локальный запуск

Нужны Node.js 22.12 или новее (лучше 24 LTS) и Python 3.11 или новее.

```bash
cp .env.example .env
```

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Frontend, во втором терминале:

```bash
cd frontend
npm install
npm run dev
```

Откройте http://localhost:3000 и нажмите «Открыть рабочее пространство» или `Enter`. Внизу слева должно появиться «API в сети». Клавиша `?` показывает все горячие клавиши.

Проверки:

```bash
cd frontend && npm run check && npm run build
```

```bash
cd backend && pytest && ruff check . && ruff format --check .
```

```bash
backend/.venv/bin/ruff check scripts && backend/.venv/bin/ruff format --check scripts
```

`npm run check` запускает typecheck, eslint, тесты и prettier.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `LITTORA_ENVIRONMENT` | `local` | `local`, `development`, `staging` или `production` |
| `LITTORA_LOG_LEVEL` | `INFO` | уровень логов backend |
| `LITTORA_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | разрешённые origin через запятую |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | адрес backend для браузера; `/` — тот же адрес, что у фронтенда |
| `NEXT_PUBLIC_DEMO_FIXTURES` | `true` | показывать ли демо-данные при старте |
| `LITTORA_API_PROXY_TARGET` | не задан | куда Next.js проксирует `/api/*`; в compose — `http://backend:8000` |
| `LITTORA_FRONTEND_PORT`, `LITTORA_BACKEND_PORT` | `3000`, `8000` | порты на хосте для Docker Compose |

`.env` в git не попадает. Ключи сервисов, например Copernicus Marine, хранятся только в нём.

## Данные

Главный источник для обучения, валидации и метрик — официальный датасет кейса, его выдадут организаторы. Всё остальное — внешние открытые данные: они нужны для предобучения, базовой модели, аугментаций и проверки гипотез. Эти группы не смешиваются.

```
data/
  sources.toml   каталог внешних источников: ссылка, лицензия, роль, регион   в git
  aoi/           районы интереса в морях России                               в git
  manifests/     что скачано: файлы, размеры, md5                             в git
  case/          официальный датасет кейса, как выдали                        не в git
  external/      внешние данные, по папке на источник                         не в git
  interim/       промежуточные результаты                                     не в git
  processed/     готовое к обучению и инференсу, по папке на источник         не в git
```

Скрипты:

- `fetch.py` — внешние наборы, только стандартная библиотека Python. Докачивает после обрыва и сверяет md5.
- `scenes.py` — снимки Sentinel-2 по районам. Для вырезки нужен rasterio.
- `inventory.py` — опись датасета кейса.

```bash
python3 scripts/data/fetch.py list
```

```bash
python3 scripts/data/fetch.py download mados --yes
```

```bash
python3 scripts/data/fetch.py unpack mados
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/data/requirements.txt
```

```bash
.venv/bin/python scripts/data/scenes.py fetch --aoi neva-bay --scenes 5
```

Когда выдадут датасет кейса, его кладут в `data/case/` как есть и записывают опись:

```bash
.venv/bin/python scripts/data/inventory.py case
```

Основные внешние источники (полный список — `fetch.py list`):

| Источник | Что это | Лицензия |
|---|---|---|
| [MARIDA](https://doi.org/10.5281/zenodo.5151941) | 1 381 патч Sentinel-2 с масками 15 классов, включая мусор, саргассум и пену | CC BY 4.0 |
| [MADOS](https://doi.org/10.5281/zenodo.10664073) | 2 803 кропа Sentinel-2 с масками мусора, нефти и двойников | CC BY 4.0 |
| [Plastic Litter Project](https://plp.aegean.gr) 2019, 2021, 2022–23 | мишени с известной долей пластика в пикселе, предел обнаружения | CC BY 4.0 |
| [Litter Windrows Catalogue](https://doi.org/10.5281/zenodo.11045944) | 14 374 полосы мусора в Средиземном море со спектрами | CC BY 4.0 |
| [marinedebrisdetector](https://github.com/MarcCoru/marinedebrisdetector) | готовые кропы Sentinel-2 для обучения и валидации | как у исходных наборов |
| [Sentinel-2 L2A, Earth Search](https://earth-search.aws.element84.com/v1) | снимки без регистрации, основной путь к данным | Copernicus |
| [Copernicus Marine](https://marine.copernicus.eu) | течения и волны для дрейфа по всем морям России, кроме Каспия | Copernicus Marine, нужен аккаунт |
| [«Дальние Зеленцы», 2023](https://www.kaggle.com/datasets/olgabilousova/marine-monitoring-autumn-2023-dalnie-zelentsy) | плавающий мусор с судовой камеры, Баренцево и Карское моря | CC BY-SA 4.0 |
| [EMODnet beach litter](https://emodnet.ec.europa.eu/en/marine-litter) | мусор на пляжах, есть российское побережье Чёрного моря и Финского залива | CC BY 4.0 |

По морям России:

- Размеченных спутниковых данных по плавающему мусору в открытом доступе нет. Поэтому модели предобучаются на зарубежных наборах и проверяются на снимках российских районов.
- В `data/aoi/russia.geojson` — 33 района во всех российских морях: порты, устья рек, проливы. По каждому уже найдены чистые летние сцены Sentinel-2.
- Для Каспия нет ни одной модели течений, дрейф там оценивается только по ветру и волнам.
- Для Copernicus Data Space в форме регистрации нет России. Снимки берутся из Earth Search: там регистрация не нужна.

## Следующие шаги

1. Разобрать датасет кейса: опись, формат меток, каналы, уровень обработки. Написать загрузчик в `ml/`.
2. Базовая модель: попиксельный классификатор по каналам Sentinel-2 и индексам FDI, NDVI, FAI. Учить на MARIDA и MADOS, проверять на данных кейса.
3. Сегментация (U-Net, SegFormer или MariNeXt) с предобучением на MADOS.
4. Контракт результатов: пятна-кандидаты в GeoJSON, доля покрытия и неопределённость в COG. Отдать их через backend в интерфейс.
5. Каталог сцен Sentinel-2 в backend, затем дрейф: OpenDrift с течениями Copernicus Marine и ветром.

## Подложки карты

- EOX Sentinel-2 cloudless — CC BY-NC-SA 4.0, только для некоммерческого показа. Contains modified Copernicus Sentinel data.
- OpenFreeMap — © OpenMapTiles, данные © OpenStreetMap (ODbL).
- NASA GIBS.

Атрибуция показана в интерфейсе: строка состояния → «Источники».
