"""Execute an analysis notebook over the saved experiments; no test-based model tuning."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import nbformat
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[2]


def main():
    cells = []

    def md(text):
        cells.append(nbformat.v4.new_markdown_cell(text))

    def code(text):
        cells.append(nbformat.v4.new_code_cell(text))

    md("""# Дополнительные данные: EMBLAS, MADOS, PLP2019 и ERA5

Исследовательские эксперименты Littora, 26.09.2026. **Операционная модель и исходный T3 не заменены.**

[Протокол](../ml/expansion/protocol.md) фиксирует модели, пороги и разделение данных. Метки разных задач сохраняются отдельно: всё наблюдённое макролиттерное загрязнение в items/km², Marine Debris на спутниковом снимке и доля пластикового покрытия в %.

MADOS не содержит пригодной геопривязки и дат отдельных кропов; независимость от MARIDA по месту/времени не доказана. Сравнение на MARIDA — development benchmark, а не новый внешний test. Test не использован для выбора гиперпараметров.""")
    code("""from pathlib import Path
import hashlib, json, platform, sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display
ROOT=Path.cwd()
T=ROOT/'reports/expansion/tables'
F=ROOT/'reports/expansion/figures'
F.mkdir(exist_ok=True)
plt.rcParams.update({'figure.dpi':120,'axes.spines.top':False,'axes.spines.right':False})
def read(name): return pd.read_csv(T/(name+'.csv'))
def save(name):
    plt.tight_layout();plt.savefig(F/(name+'.png'),dpi=160,bbox_inches='tight');plt.show();plt.close()
emblas=read('emblas_events_pending');plp=read('plp2019_pixel_cover');inventory=read('mados_inventory')
metrics=read('detector_metrics');intervals=read('detector_bootstrap');weather=read('weather_oof_metrics')
assert len(emblas)==302 and not emblas.t3_eligible.any()
assert len(inventory)==2803 and inventory.groupby('group').split.nunique().max()==1
display(pd.DataFrame([
    {'source':'EMBLAS','unit':'visual session','rows':len(emblas),'status':'pending coordinates; 0 T3 additions'},
    {'source':'MADOS','unit':'240×240 crop','rows':len(inventory),'status':'scene split; geotime metadata missing'},
    {'source':'PLP2019','unit':'UAV-labelled S2 pixel','rows':len(plp),'status':f'{plp.spatial_match_valid.sum()} spatial matches / 5 dates'},
    {'source':'ERA5','unit':'prior-day context','rows':len(read('era5_event_context')),'status':'74 existing events; not new density labels'}]))""")
    md("""## EMBLAS: подготовлено 302 сессии, допуск в T3 пока закрыт

В [исходной Table S2](https://ars.els-cdn.com/content/image/1-s2.0-S0269749122010302-mmc2.xlsx?download=true) площадь уже есть у всех строк. Не хватает подтверждённой связи Session ID с координатами и часового пояса StartTime. Счётчики, опубликованная плотность и N/A сохранены отдельно, нулевые сессии не удалены. Шесть российских записей в Table S1 — экспедиции/программы, не шесть сессий. Проверенные источники и черновик запроса: [журнал поиска](../docs/emblas-coordinate-search.md).""")
    code("""display(read('emblas_year_summary'))
display(emblas.groupby('basin_sector').agg(events=('event_id','size'),zeros=('is_observed_zero','sum'),area_km2=('area_km2','sum')))
fig,axs=plt.subplots(1,2,figsize=(10,3.7))
for year,g in emblas.groupby('year'):
    axs[0].hist(np.log1p(g.reported_density_items_km2),bins=20,alpha=.55,label=str(int(year)))
    axs[1].scatter(g.area_km2,g.items_count,s=14,alpha=.55,label=str(int(year)))
axs[0].set(xlabel='log(1 + published items/km²)',ylabel='Sessions');axs[0].legend()
axs[1].set(xlabel='Surveyed area, km²',ylabel='Observed item count');axs[1].legend()
save('01_emblas_effort_and_density')
print('Area-weighted density:',emblas.items_count.sum()/emblas.area_km2.sum(),'items/km²')
print('True observed zeros:',int(emblas.is_observed_zero.sum()))""")
    md("""## MADOS: разметка и перенос детектора

[MADOS v1](https://zenodo.org/records/10664073): исходные 174 сцены, 2803 кропа, разреженная разметка. Не размеченный класс 0 не считается водой/отрицательной меткой. Confidence 0 и невалидные спектры исключаются. Class 6 означает нефтяное пятно, class 12 — волны и следы судов; номера остальных классов нельзя безусловно переносить из MARIDA.

11 каналов rhorc объединены в физическом порядке Sentinel-2; 20/60 м увеличены nearest-neighbour. MADOS-only и joint используют одинаковый RF и подбирают порог только по MADOS validation. У прежнего детектора сохранён прежний порог MARIDA. Разности метрик отражают **обучающие данные вместе с калибровкой порога**.

Скрининг полных спектров сравнивает MADOS со всеми исходными split MARIDA; любая найденная сцена исключается целиком из эксперимента. Отсутствие точного совпадения не исключает повторную обработку или соседнюю съёмку того же события.""")
    code("""display(read('mados_split_summary'))
print('Exact matching spectra:',int(inventory.marida_exact_spectral_matches.sum()))
print('Excluded groups:',inventory.loc[~inventory.cross_source_screen_pass,'group'].nunique())
print('Invalid labelled pixels:',int(inventory.invalid_labelled_pixels.sum()))
print('Labelled without confidence:',int(inventory.labelled_without_confidence.sum()))
sys.path.insert(0,str(ROOT/'ml/expansion'))
from mados import CLASSES
counts=pd.DataFrame({'class_id':list(CLASSES),'class_name':list(CLASSES.values()),
    'pixels':[int(inventory['class_'+str(k)].sum()) for k in CLASSES]})
counts.to_csv(T/'mados_class_counts.csv',index=False)
fig,ax=plt.subplots(figsize=(10,4))
ax.barh(counts.class_name,counts.pixels,color='#2374ab');ax.set_xscale('log');ax.invert_yaxis()
ax.set(xlabel='Usable annotated pixels (log scale)',title='MADOS class distribution')
save('02_mados_classes')
display(read('detector_thresholds'))
display(metrics[['dataset','model','pixels','positive_pixels','precision','recall','f1','iou','average_precision']].round(4))
display(intervals.round(4))
fig,axs=plt.subplots(1,2,figsize=(11,4))
for ax,(name,g) in zip(axs,metrics.groupby('dataset')):
    ax.bar(g.model,g.f1,color=['#20a386','#7a8a99','#2374ab'])
    for x,(_,r) in enumerate(g.iterrows()):
        ci=intervals[(intervals.dataset==name)&(intervals.comparison==r.model)].iloc[0]
        ax.vlines(x,ci.low,ci.high,color='black',lw=1.5);ax.text(x,r.f1+.015,f'{r.f1:.3f}',ha='center')
    ax.set_ylim(0,1);ax.set(title=name,ylabel='F1, scene/group bootstrap 95% interval');ax.tick_params(axis='x',rotation=15)
save('03_detector_comparison')
errors=read('detector_errors_by_class')
display(errors[(errors.dataset=='mados_test')&errors.class_id.isin([1,4,5,6,9,12,13])].round(4))""")
    md("""## PLP2019: покрытие пикселя, независимая дата

[PLP2019](https://zenodo.org/records/3752719) содержит 65 точек с долями материалов за пять дат. Два пикселя 18.05.2019 находятся вне допуска сопоставления с NetCDF; они сохранены с причиной исключения. Для оставшихся 63 отклонение центров менее метра. Все сохранённые l2_flags равны 0. Тростник — отдельная доля, не пластик.

Данные **rhos**, не rhorc: текущий MARIDA RF на них не применяется. Отдельная Ridge(alpha=10) с нормализацией только по train, leave-one-date-out, предсказывает процент покрытия. Контроль — среднее train-дней. Пять дат одного участка и малого числа искусственных мишеней не характеризуют весь диапазон природных условий.""")
    code("""display(plp.groupby('date').agg(pixels=('date','size'),spatial_matches=('spatial_match_valid','sum'),mean_plastic_pct=('plastic_cover_pct','mean')))
display(plp.loc[~plp.spatial_match_valid,['date','pixel_name','match_distance_m','exclusion_reason']])
display(read('plp2019_date_holdout_metrics').round(4))
pred=read('plp2019_date_holdout_predictions')
fig,ax=plt.subplots(figsize=(6,4))
for date,g in pred[pred.model=='ridge_rhos'].groupby('date'): ax.scatter(g.observed,g.predicted,label=date,s=24,alpha=.75)
ax.plot([0,70],[0,70],':',color='gray');ax.set(xlabel='UAV plastic cover, %',ylabel='Held-out date prediction, %')
ax.legend(fontsize=8);save('04_plp_date_holdout')""")
    md("""## ERA5: проверка пользы погодного контекста

74 исходных визуальных события, исходные группы/folds EDA. [ERA5 через Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api): 0.25°, nearest sea grid cell, UTC; средний/максимальный ветер, средние u/v и осадки **за предшествующий календарный день**. Это не измеренные течения и не восстановленное точное время учёта.

Две фиксированные модели RF log1p: координаты + сезон и те же признаки + погода. Профили Северного и Чёрного морей оцениваются раздельно. Положительный paired MAE gain означает улучшение от погоды. Отрицательное значение означает ухудшение.""")
    code("""display(weather.round(4));display(read('weather_paired_gain').round(4))
fig,axs=plt.subplots(1,2,figsize=(11,4))
for ax,(profile,g) in zip(axs,weather.groupby('profile')):
    ax.bar(['Location/season','+ prior-day weather','Train median'],g.mae_items_km2,color=['#2374ab','#20a386','#7a8a99'])
    ax.set(title=profile,ylabel='Out-of-fold MAE, items/km²');ax.tick_params(axis='x',rotation=15)
save('05_weather_ablation')""")
    md("""## Выводы и необходимые данные

1. Для T3 сильнейший недостающий блок — оригинальная таблица EMBLAS `Session ID ↔ start/end/midpoint coordinates`, timezone, принадлежность экспедиции и условия повторного использования. Для спутниковых пар полезнее трек с временем, чем одна точка. Уже подготовленные 302 сессии включают 40 настоящих нулей.
2. Для проверяемого переноса MADOS нужны реальные Sentinel-2 product IDs, даты и геометрии кропов; затем общий split MARIDA/MADOS по месту и времени. Без этого совместное обучение остаётся экспериментом.
3. Для Littora L2A нужны идентичные сцены/разметка в L2A и ACOLITE rhorc, единый контроль масштаба, offset и масок. Совпадение количества каналов не обеспечивает сопоставимость продуктов.
4. Для оценки концентрации нужны новые независимые визуальные трансекты (включая нули), площадь полосы, счётчик, порог размера, усилие наблюдателя и синхронная съёмка. Пиксельная вероятность детектора и процент покрытия PLP не являются items/km².
5. Погодные признаки и PLP в проверенных простых моделях не дали подтверждённого улучшения; дальнейшую сложность следует проверять на новых группах, не подбирать по уже увиденному test. Морские течения/волны ещё не включены; windrows и другие наборы остаются отдельными кандидатами, а не выполненными экспериментами.

[Поиск EMBLAS и точный запрос владельцу](../docs/emblas-coordinate-search.md). Письма автоматически не отправлялись.""")
    code("""# Recompute saved detector decisions independently from scores.
from marida.models import confusion, scores_from_counts
thresholds=read('detector_thresholds').set_index('model').threshold
for dataset in metrics.dataset.unique():
    a=np.load(ROOT/'data/processed/expansion'/f'{dataset}_predictions.npz')
    assert (a['y']>0).all()
    for model,threshold in thresholds.items():
        c=confusion(a['y']==1,a[model+'_score']>=threshold)
        expected=metrics[(metrics.dataset==dataset)&(metrics.model==model)].iloc[0]
        assert all(c[k]==expected[k] for k in ['tp','fp','fn','tn'])
        assert np.isclose(scores_from_counts(**c)['f1'],expected.f1)
files=sorted(T.glob('*.csv'))+[ROOT/'ml/expansion/protocol.md',ROOT/'data/case/macroplastic_marine_samples.csv']
hashes=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files if p.name!='artifact_hashes.csv']
pd.DataFrame(hashes).to_csv(T/'artifact_hashes.csv',index=False)
summary={'emblas_sessions':len(emblas),'emblas_zeros':int(emblas.is_observed_zero.sum()),'t3_added':0,
         'mados_patches':len(inventory),'mados_scenes':inventory.scene_id.nunique(),
         'mados_usable_pixels':int(inventory.usable_pixels.sum()),
         'cross_source_matching_spectra':int(inventory.marida_exact_spectral_matches.sum()),
         'cross_source_excluded_groups':inventory.loc[~inventory.cross_source_screen_pass,'group'].nunique(),
         'plp_pixels':len(plp),'plp_matched_pixels':int(plp.spatial_match_valid.sum()),
         'detector_metrics':metrics.to_dict('records'),'weather_metrics':weather.to_dict('records'),
         'python':sys.version,'platform':platform.platform(),'production_model_changed':False}
(ROOT/'reports/expansion/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('Saved predictions reproduce all detector confusion matrices and F1 values. Report complete.')""")
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata.kernelspec = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    output = ROOT / "notebooks/03_data_expansion.ipynb"
    with TemporaryDirectory(prefix="littora-expansion-kernel-") as temp:
        d = Path(temp) / "python3"
        d.mkdir()
        (d / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [
                        sys.executable,
                        "-m",
                        "ipykernel_launcher",
                        "-f",
                        "{connection_file}",
                    ],
                    "display_name": "Python 3",
                    "language": "python",
                }
            )
        )
        km = KernelManager(
            kernel_name="python3",
            kernel_spec_manager=KernelSpecManager(kernel_dirs=[temp]),
        )
        try:
            NotebookClient(
                notebook,
                km=km,
                timeout=600,
                resources={"metadata": {"path": str(ROOT)}},
            ).execute(cleanup_kc=True)
        finally:
            nbformat.write(notebook, output)
    html, _ = HTMLExporter(template_name="lab").from_notebook_node(notebook)
    (ROOT / "reports/expansion/data_expansion.html").write_text(html)
    import hashlib

    tracked = list((ROOT / "ml/expansion").glob("*.py"))
    tracked += [
        ROOT / "ml/expansion/requirements.lock.txt",
        ROOT / "ml/expansion/protocol.md",
    ]
    tracked += list((ROOT / "data/processed/expansion").glob("*.joblib"))
    tracked += list((ROOT / "data/processed/expansion").glob("*predictions.npz"))
    tracked += [ROOT / "data/processed/expansion/model_metadata.json"]
    tracked += [
        ROOT / f"data/manifests/{source}.json"
        for source in ["marida", "mados", "plp2019"]
    ]
    tracked += [ROOT / "data/case/macroplastic_marine_samples.csv"]
    manifest = {"created_on": "2026-09-26", "seed": 42, "files": []}
    for path in tracked:
        manifest["files"].append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (ROOT / "reports/expansion/run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
