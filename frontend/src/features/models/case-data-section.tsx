import { ReportSection } from "./report-section";

const ROWS: readonly {
  source: string;
  where: string;
  method: string;
  events: number;
  target: string;
  imagery: string;
}[] = [
  {
    source: "S1",
    where: "Тихий океан, мусорное пятно, 2015–2016",
    method: "тралы 5–50 см и аэросъёмка",
    events: 181,
    target: "пластик 5–50 см, трал — 83 события",
    imagery:
      "снимков нет: открытый океан Sentinel-2 не снимает (83); 98 событий вне целевой величины",
  },
  {
    source: "S2",
    where: "Саргассово море, апрель 2015",
    method: "визуальные трансекты, пластик от 2 см",
    events: 63,
    target: "основная величина: суммарный пластик — 63 события",
    imagery: "до запуска Sentinel-2A (51); нет сцены в окне (10); большой сдвиг по времени (2)",
  },
  {
    source: "S3",
    where: "Северное море, 2014 и 2016",
    method: "визуальный учёт, мусор от 2 см",
    events: 41,
    target: "весь плавающий мусор — 41 событие",
    imagery: "большой сдвиг по времени (23); облачность тайла (7); нет сцены (7); до запуска (4)",
  },
  {
    source: "S4",
    where: "Чёрное море, рейс DOORS, июнь 2024",
    method: "визуальный учёт, мусор от 2,5 см",
    events: 33,
    target: "весь плавающий мусор — 33 события",
    imagery:
      "7 пар со снимком того же дня; сдвиг по времени (21); облака (4); качество не подтверждено (1)",
  },
];

export function CaseDataSection({ index }: { index: number }) {
  return (
    <ReportSection id="case" index={index}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px] leading-4">
          <thead>
            <tr className="border-b border-text-primary text-left text-text-secondary">
              <th className="pb-2 font-medium">Источник</th>
              <th className="pb-2 pl-3 font-medium">Где и когда</th>
              <th className="pb-2 pl-3 font-medium">Метод</th>
              <th className="pb-2 pl-3 text-right font-medium">Событий</th>
              <th className="pb-2 pl-3 font-medium">В целевой величине</th>
              <th className="pb-2 pl-3 font-medium">Снимки Sentinel-2</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.source} className="border-b border-line-hairline align-top">
                <th
                  scope="row"
                  className="py-2 text-left font-mono font-semibold text-text-primary"
                >
                  {row.source}
                </th>
                <td className="py-2 pl-3 text-text-primary">{row.where}</td>
                <td className="py-2 pl-3 text-text-secondary">{row.method}</td>
                <td className="py-2 pl-3 text-right font-mono text-text-primary">{row.events}</td>
                <td className="py-2 pl-3 text-text-secondary">{row.target}</td>
                <td className="py-2 pl-3 text-text-secondary">{row.imagery}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[12px] leading-[18px] text-text-tertiary">
        Всего 935 записей и 318 событий. Причины по каждому событию и каждой паре — в реестре пар;
        измерения на карте показаны отдельным знаком и не смешиваются с оценками модели.
      </p>
    </ReportSection>
  );
}
