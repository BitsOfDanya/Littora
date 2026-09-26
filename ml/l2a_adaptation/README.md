# L2A adaptation

Проверка обучения на целевом продукте и отдельного эффекта калибровки порога. Все решения до test описаны в protocol.md. Старые данные/модели не перезаписываются; Black Sea reserved_holdout остаётся закрытым от модельных предсказаний.

Из корня репозитория, существующее ml/.venv и предыдущие артефакты MARIDA/expansion:

```sh
ml/.venv/bin/python ml/l2a_adaptation/acquire.py prepare
ml/.venv/bin/python ml/l2a_adaptation/acquire.py download
ml/.venv/bin/python ml/l2a_adaptation/acquire.py extract
ml/.venv/bin/python ml/l2a_adaptation/train.py
ml/.venv/bin/python ml/l2a_adaptation/report.py
ml/.venv/bin/python -m pytest -q ml/l2a_adaptation/test_l2a_contracts.py
```

prepare проверяет все MARIDA scenes по публичному STAC и фиксирует выборку до inference. Реестр выбранных патчей не изменяется автоматически при повторном поиске. download сохраняет кропы, использует кеш и записывает ошибки; при сбое повторить download. extract не заполняет пропуски и сохраняет одинаковые валидные размеченные пиксели обоих продуктов. Геометрия, confidence и классы исходного MARIDA проверены предыдущим этапом и повторно проверяются при объединении.

Зависимости из ml/validation_bridge/requirements.lock.txt. Требуются исходные MARIDA TIFF, инвентаризация и строгие split/group, прежние MARIDA/joint RF. Сеть нужна только prepare/download (Earth Search C1 L2A; без credentials). Не восстанавливать отсутствующие сцены соседними датами. Для пересмотра протокола создать отдельную версию данных/результатов.

train обучает RF на L2A train и контроль на rhorc тех же train-пикселей. Веса и validation-пороги сохраняются до test inference в frozen_before_test.json. Одинаковые гиперпараметры, один seed, без выбора варианта по test. Сравниваются 6 заранее заданных вариантов. Тест уже development benchmark; это не независимый региональный скор.

Отчёт: reports/l2a_adaptation/conclusions.md, l2a_adaptation.html, notebooks/06_l2a_adaptation.ipynb. Веса и scores: data/processed/l2a_adaptation/. Для восстановления label reference см. selected_patches.csv + paired_pixels.npz (patch_index относится к selection_index, row/col — к исходной сетке). Class 0 никогда не считается negative. Counts/доли покрытия не переводятся в items/km².

До обучения сделана документированная поправка покрытия train: один дополнительный патч 4-9-19_16PCC_32 с 18 Foam-пикселями. prepare воспроизводит эту поправку детерминированно, если первоначальная выборка не содержит Foam в train. Validation/test не меняются; исходный выбор сохранён отдельно.
