import Image from "next/image";
import { apiUrl } from "@/lib/api/client";
import { ReportSection } from "./report-section";

const VERDICTS: readonly { tone: string; title: string; text: string }[] = [
  {
    tone: "border-state-ok",
    title: "Можно доверять",
    text: "Зоны на пригодном снимке без флагов. На отложенных снимках MARIDA по размеченным пикселям: из 100 пикселей, отмеченных сервисом, около 87 — мусор; из 100 пикселей мусора сервис находит около 95. На неразмеченной воде — около 250 лишних пикселей на 100 км².",
  },
  {
    tone: "border-state-caution",
    title: "Проверить",
    text: "Зоны с флагами «вероятно судно», «рядом сооружение», «порт», «неустойчива к поворотам»: это частые источники ложных срабатываний. Зона не скрыта — решение за специалистом, отметка команды копится для дообучения.",
  },
  {
    tone: "border-state-alarm",
    title: "Не выводить",
    text: "Концентрацию в шт./км² по площади зоны: отдельные предметы от 2 см в пикселе 10 м не видны. Концентрация берётся из полевой модели со статусом «исследовательская оценка» и интервалом.",
  },
];

export function ReadingGuide({ index }: { index: number }) {
  return (
    <ReportSection id="guide" index={index}>
      <div className="grid grid-cols-12 gap-x-6 gap-y-4">
        {VERDICTS.map((item) => (
          <div
            key={item.title}
            className={`col-span-12 border-l-2 pl-3 @4xl:col-span-4 ${item.tone}`}
          >
            <p className="text-[13px] leading-5 font-semibold text-text-primary">{item.title}</p>
            <p className="mt-1 text-[12px] leading-[18px] text-text-secondary">{item.text}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 text-[12px] leading-[18px] text-text-tertiary">
        Практический порядок: зона детектора → карточка зоны (флаги, устойчивость, сопоставление с
        измерениями с судна) → при необходимости план обследования судном или БПЛА. Все числа ниже —
        из файлов оценки в репозитории, test посчитан один раз.
      </p>
    </ReportSection>
  );
}

const FIGURES: readonly { key: string; title: string; caption: string; wide?: boolean }[] = [
  {
    key: "plp",
    title: "Вблизи · мишени известного размера",
    caption:
      "Plastic Litter Project, Лесбос, окно 400 м. Сетка HDPE 609 м² и смесь с деревом найдены (p 0,97–1,00), связка бутылок и пакетов 120 м² — p 0,94, бутылки 13 м² не видны, природная древесина — ложная тревога (p 0,57).",
    wide: true,
  },
  {
    key: "best",
    title: "Удачные обнаружения",
    caption:
      "Патчи test MARIDA ≈2,5×2,5 км: снимок, разметка, вероятность, итог. Полосы мусора вдоль фронтов найдены без ложных пикселей.",
  },
  {
    key: "false_alarms",
    title: "Ложные срабатывания на сложном фоне",
    caption:
      "Блики на волнах и суда со следом — главные источники ошибок; для них в сервисе флаги «вероятно судно» и «неустойчива к поворотам».",
  },
  {
    key: "worst",
    title: "Худшие случаи",
    caption: "Патчи test с наибольшим числом пропусков и ложных пикселей — границы достоверности.",
  },
  {
    key: "pairs",
    title: "Издалека · судно и спутник в один день",
    caption:
      "Чёрное море, круг 6 км вокруг трансекта. Судно насчитало 193–587 шт./км², на снимке выше порога 0–58 пикселей: отдельные предметы спутник не видит.",
  },
];

export function GallerySection({ index }: { index: number }) {
  return (
    <ReportSection id="gallery" index={index}>
      <div className="grid grid-cols-12 gap-x-6 gap-y-8">
        {FIGURES.map((figure) => {
          const src = apiUrl(`/models/figures/${figure.key}`);
          return (
            <figure
              key={figure.key}
              className={`col-span-12 m-0 min-w-0 ${figure.wide ? "" : "@4xl:col-span-6"}`}
            >
              <a href={src} target="_blank" rel="noreferrer" className="block">
                <Image
                  src={src}
                  alt={figure.title}
                  width={1600}
                  height={900}
                  unoptimized
                  className="h-auto w-full rounded-[2px] border border-line-hairline bg-white"
                />
              </a>
              <figcaption className="mt-2 text-[12px] leading-[18px] text-text-secondary">
                <span className="font-semibold text-text-primary">{figure.title}.</span>{" "}
                {figure.caption}
              </figcaption>
            </figure>
          );
        })}
      </div>
    </ReportSection>
  );
}
