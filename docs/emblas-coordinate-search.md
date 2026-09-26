# EMBLAS: поиск координат для 302 сессий

Проверено 26 сентября 2026 года. **Открытую таблицу координат, однозначно связанную с 302 сессиями González-Fernández et al. (2022), найти не удалось. Новых событий в T3 не добавлено.** Нашлись исходные географические записи в RedMarLitter и подтверждение передачи координат авторами другим исследователям. Ниже — проверенные результаты и точный недостающий экспорт.

## Что уже есть в приложении к статье

[Оригинальный Excel](https://ars.els-cdn.com/content/image/1-s2.0-S0269749122010302-mmc2.xlsx?download=true), лист `TableS2_Monitoring sessions`, строки 2–303:

- 302 уникальных `Monitoring Session ID`, 132 сессии за 2017 и 170 за 2019 год.
- У всех заполнены `StartTime`, длительность, высота наблюдения, ширина полосы, длина трансекты, число предметов, **`SurveyedArea (km2)`** и плотность. Координат, исходного идентификатора JRC, страны и судна на этом листе нет. Часовой пояс `StartTime` заголовком не указан.
- Сумма площадей 93.92213002 км², число предметов 7655; 40 нулевых наблюдений. Площадь не требуется восстанавливать из координат или из плотности. Опубликованные округления необходимо сохранить.
- `TableS1_EMBLAS surveys20172019!B8:F13` содержит **шесть российских экспедиций/программ**, а не шесть отдельных сессий. Российские сессии нельзя точно посчитать из S2 без связи с исходными экспедициями/геометрией.

Методика статьи: визуальный учёт всего плавающего мусора >2.5 см, плотность по обследованной полосе. Для карт авторы использовали середины трансект. Это кандидат в профиль T3 «весь мусор, визуальный учёт» с сохранением собственного порога размера и протокола, а не автоматически совместимая метка пластика. [Статья, разделы 2.1–2.2](https://rodin.uca.es/bitstream/10498/27455/1/APC_2022_088.pdf).

Скачанный Excel побайтно соответствует имеющемуся manifest: MD5 `2118e64c762e108f64050e9a1e79eb4e`, 58688 байт.

## EMODnet Chemistry

В проверенном [каталоге ERDDAP](https://erddap.emodnet-chemistry.eu/erddap/info/index.html) есть `FLOATING_MICROLITTER`, пляжные и донные наборы, но нет отдельного набора плавающего макромусора. Это результат проверки данного каталога, не доказательство отсутствия исходных записей во всех узлах SeaDataNet/CDI.

[Сообщение EMBLAS о передаче данных EMODnet](https://emblasproject.org/gallery/emblas-provided-data-on-marine-litter-to-emodnet) касается **пляжного** мусора. [Раздел руководств EMODnet](https://emodnet.ec.europa.eu/en/tools-guidelines) ссылается на предложение по управлению данными floating macro litter, DOI `10.6092/a0e453b0-100b-4a9e-8f27-bbfb2337717c`; сам документ не является набором наблюдений.

## Отчёты EMBLAS и собственная база

Проверены основной [отчёт 2017 года](https://emblasproject.org/wp-content/uploads/2022/03/EMBLAS-II_NPMS_JOSS_2017_ScReport_ISBN-978-617-7953-62-2.pdf), его [приложения](https://emblasproject.org/wp-content/uploads/2022/03/EMBLAS-II_NPMS_JOSS_2017_ScReport_ANNEXES-1-7_Fin_ISBN-978-617-7953-61-5.pdf), [итоговый отчёт 2016–2019](https://emblasproject.org/wp-content/uploads/2022/03/EMBLAS_Scientific-Report_ISBN-978-617-8111-01-4-web.pdf) и [приложение к нему](https://emblasproject.org/wp-content/uploads/2025/03/EMBLAS-Annex-Final-Scientific-Report.pdf).

- В разделе VII.2.1 отчёта 2017 года, стр. 533–535, есть карты и сводки, а также указание на передачу исходных записей в базы BSC/JRC. Приведены **144 трансекты**, тогда как статья включает 132 за этот год. Причину различия здесь не устанавливаем.
- В итоговом отчёте, VIII.3.1, стр. 311–313, для 2019 года совпадают 170 сессий, 2032 км, около 30 км² и 2714 предметов. Сессионной таблицы координат в этом разделе нет.
- В приложениях не обнаружен экспорт нужных 302 сессий. Координаты станций химического/биологического отбора не подставлялись вместо трансект мусора.
- Итоговый отчёт, XI.3, стр. 402–407, описывает отдельный каталог floating marine litter в Black Sea Water Quality Database и Web-GIS. При проверке `https://blackseadb.org/` и HTTP-версии получен 403; `https://ims.sea.gov.ua/emblas/` и каталог ArcGIS не ответили за 20 секунд. Содержимое этих сервисов проверить не удалось.

## RedMarLitter: координаты есть, надёжного объединения пока нет

[EMBLAS подтверждает](https://emblasproject.org/archives/3615) передачу части грузинских морских и речных наблюдений в [RedMarLitter](https://map.redmarlitter.eu/en/database). Публичная выгрузка работает: скачаны `waste.xlsx` за 2017–2019 и GeoJSON из используемого страницей API.

Результат: 905 записей waste. Для воспроизводимой проверки выделены 665 точек с долготой >38°E; их названия мест относятся к грузинскому побережью и устьям рек. Это географический фильтр, а не доказанная выборка EMBLAS-2022.

- У всех этих 665 записей отсутствует концентрация по видам. У 664 нет второй пары координат. Есть ширина у части записей, но нет длины/площади сессии и времени начала/окончания.
- Записи включают отдельные предметы, медуз, листья, перья, пропуски и скопления мусора. Их число не является готовым числителем плотности.
- Ни одна из шести опубликованных дат этой группы не совпала с календарной датой S2. Идентификаторы вида `28.05.16M_` встречаются с датой `02.10.2019`: смысл даты требует уточнения, она может не соответствовать исходному наблюдению.

Есть **кандидат на связь**, требующий проверки: `Batumi_27.` имеет ширину 25 м и 94 записи с датами 28–29 октября 2019 года. Сессия S2 №302 началась 27 октября 2019 в 11:38; ширина 25 м, длина 19390 м, площадь 0.48475 км², 12 предметов. У RedMarLitter этой группы 13 записей с названиями отдельных антропогенных предметов и ещё одна `Litter patch >20 items`, а также природные объекты/пропуски. Сходства недостаточно для объединения: расходятся дата и числитель, нет полного трека и общего ID. Координаты отдельных предметов нельзя объявить серединой трансекты.

Исходные загрузки сохранены в `data/external/emblas-floating-litter/` и `data/external/redmarlitter-research/`. Параметры запросов, контрольные суммы и результаты проверки — `reports/emblas/search-audit.json`. Лицензия статьи не переносится автоматически на RedMarLitter.

## Самый прямой путь к недостающему экспорту

В [Castro-Rosero et al. (2025), раздел 2.4, стр. 4](https://diposit.ub.edu/bitstreams/f41050fc-482e-47a4-9dde-bb724bab6280/download), прямо сказано, что данные мусора **и их местоположения** из EMBLAS-2017 получены из работы 2022 года и через личное общение с её первым автором. Использована часть набора за август–сентябрь, семь дней наблюдений. Это подтверждает существование координатных данных по меньшей мере для этой части набора, но не открытого полного экспорта 302 сессий. В разделе Data availability: данные по запросу.

Приоритетный контакт — Daniel González-Fernández, `daniel.gonzalez@uca.es`, адрес опубликован в [карточке статьи](https://pubmed.ncbi.nlm.nih.gov/35872285/). Дополнительный адрес JRC — `JRC-FloatingLitterMonitoring@ec.europa.eu`, опубликованный в [протоколе TG ML](https://mcc.jrc.ec.europa.eu/documents/TG_ML_Meeting/TG_ML_meeting_summary_Brussels-21-22.06.2023.pdf). Сообщения никому не отправлялись.

Готовая формулировка запроса:

> We are seeking the georeferenced version of the 302 EMBLAS monitoring sessions underlying González-Fernández et al. (2022), DOI 10.1016/j.envpol.2022.119816. We already have Supplementary Table S2 with session IDs, StartTime, surveyed area, strip width, transect length, litter counts and density. Could you share a table linking those same Monitoring Session IDs to WGS84 start/end coordinates and/or the published transect midpoints, preferably with original JRC session IDs, UTC start/end times, cruise/vessel identifiers and full tracks where available? Please confirm the time zone of S2 StartTime, the inclusion of zero-count sessions, and the reuse licence. A QGIS/GeoJSON/CSV export used for Figures 1–2 would also be useful. We noticed that Castro-Rosero et al. (2025), DOI 10.1016/j.marpolbul.2025.117602, obtained the 2017 observations and locations through communication with the first author.

После получения: объединять по подтверждённому идентификатору сессии, сохранять авторскую площадь и все 40 нулей, отдельно проверять время и геометрию для спутниковых пар. До этого точное число новых пригодных событий T3 неизвестно.

## Дополнительная проверка 26.09.2026: повторное использование и JRC

- Проверена работа [Garcia-Gorriz et al., 2026](https://doi.org/10.3390/oceans7020026). Скачан доступный [архив Supplementary Materials](https://mdpi-res.com/d_attachment/oceans/oceans-07-00026/article_deploy/oceans-07-00026-s001.zip): единственный PDF, 14 страниц. Раздел S5 про EMBLAS содержит Figure S3 с месячными модельными картами, а не реестр исходных сессий. Таблицы S1–S5 посвящены литературе, источникам выбросов и Stokes drift. У [JRC145527](https://publications.jrc.ec.europa.eu/repository/handle/JRC145527) ссылки на отдельные datasets отсутствуют.
- Проверено дерево [CNR-ISMAR/pmar](https://github.com/CNR-ISMAR/pmar), связанное с DOI 10.1016/j.envsoft.2025.106822: есть код модели и полигоны границ морей, таблицы наблюдений EMBLAS не найдены.
- Актуальная [страница EMODnet Chemistry](https://emodnet.ec.europa.eu/en/chemistry) перечисляет beach/seafloor macrolitter и floating microlitter. Плавающий **макро**мусор нельзя заменять найденной коллекцией FLOATING_MICROLITTER.
- Проверен новый [портал JRC Floating Litter Monitoring](https://floating-litter-monitoring.jrc.ec.europa.eu/). Публичный endpoint `/api/Observation/GetPositionsForWelcomePage` вернул четыре демонстрируемые записи сентября 2026, не EMBLAS. Запросы чтения `/api/Observation/GetPositionsForGeoportal` и `/api/Observation/GetList` возвращают HTTP 302 на proxy/auth redirect. Наличие у оператора более ранних данных не установлено; авторизация не обходилась.
- Создана воспроизводимая таблица `reports/expansion/tables/emblas_events_pending.csv`: 302 сессии с площадью и числом предметов, 40 истинных нулей. `t3_eligible=False` для всех строк: координаты с привязкой к Session ID по-прежнему не найдены, timezone StartTime не установлен. Исходный T3 не изменён.

Сырые новые материалы сохранены в `tmp/emblas-research/`; нормализованные данные и программа подготовки — в `reports/expansion/` и `ml/expansion/field_data.py`. Следующий конкретный запрос владельцу данных уже приведён выше; автоматически не отправлялся.
