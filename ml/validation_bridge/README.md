# Validation bridge

Продолжение исследования: исходные DOORS, полевой optical matchup, парная радиометрия и будущая независимая разметка Чёрного моря. Результаты: reports/validation_bridge/summary.md, analysis.html, review_gallery.html и notebooks/04_validation_bridge.ipynb.

Из корня репозитория запускать последовательно:

```sh
ml/.venv/bin/python ml/validation_bridge/field_sources.py
ml/.venv/bin/python ml/validation_bridge/imagery.py
ml/.venv/bin/python ml/validation_bridge/review.py
ml/.venv/bin/python ml/validation_bridge/report.py
ml/.venv/bin/python -m pytest -q ml/validation_bridge/test_validation_contracts.py
```

Окружение: requirements.lock.txt и reports/validation_bridge/provenance.json. Первый запуск imagery требует исходного MARIDA, patch_inventory.csv, split_membership.csv и замороженного spectral_forest.joblib из этапа ml/marida. Модель не переобучается.

Поиск: публичный Earth Search STAC sentinel-2-c1-l2a; HTTPS range reads COG без credentials. Снимки, JSON ответов, исходные Zenodo файлы — в игнорируемом data/external/. Сохранены хеши; кеш поиска фиксирует полученный каталог и автоматически не обновляется. Для нового поиска создавать отдельный кеш, сохраняя старый. Отсутствие сцены означает отсутствие в проверенном запросе, не во всех архивах.

imagery.py сохраняет NaN для nodata, применяет scale/offset из STAC и приводит каналы к исходной сетке. Кеш кропа проверяется по product ID. Полные спектральные данные проверяются после SCL. Человеческие labels/annotations не перезаписываются. Для изменения протокола/сцены размеченного кропа создавать новый chip ID.

review.py создаёт отдельные формы двух разметчиков. Нулевые labels — неизвестные. Набор не подключён к обучающему loader; training_allowed=False. Assignment CSV — исходный шаблон распределения, статус работы хранится в формах. evaluation_ready проверяет метаданные для будущей оценки; импорт/растеризация экспертных полигонов пока не реализованы.

field_sources.py не объединяет водную оптику с litter-трансектами. Несоответствие T33 сохранено в аудите, существующая поправка case не меняется. romania_july2024_pending.csv вручную перенесена из Table 1, стр. 4 PDF Castro-Rosero et al. 2025 и визуально сверена; источники описаны в search_audit.md. Для PDF CORDIS downloadPublic возвращает HTML с refresh URL, который нужно открыть до PDF.

Тесты предназначены для исходного неразмеченного релиза: после настоящего review проверку пустых labels нужно заменить проверкой утверждённой разметки. Они проверяют nodata/offset, геопривязку, unknown vs negative и отсутствие подмены времён; научная корректность будущих labels требует отдельного аудита.
