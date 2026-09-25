import { GATE_LIVERY } from "./gate-livery";
import { WAVE_VIEW_WIDTH, areaAbove, areaBelow, wavePath } from "./chart-waves";

const DEPTH_VIEW_HEIGHT = 100;
const SHALLOW_ISOBATH = wavePath(24, 3, 11);
const MIDDLE_ISOBATH = wavePath(55, 4, 29);
const DEEP_ISOBATH = wavePath(83, 4, 47);

const FORESHORE_VIEW_HEIGHT = 24;
const FORESHORE_EDGE = wavePath(9, 3, 5, 100);

export function DepthBands() {
  return (
    <svg
      aria-hidden
      className="absolute inset-0 size-full"
      viewBox={`0 0 ${WAVE_VIEW_WIDTH} ${DEPTH_VIEW_HEIGHT}`}
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y="0"
        width={WAVE_VIEW_WIDTH}
        height={DEPTH_VIEW_HEIGHT}
        fill={GATE_LIVERY.deep}
      />
      <path d={areaAbove(MIDDLE_ISOBATH)} fill={GATE_LIVERY.middle} />
      <path d={areaAbove(SHALLOW_ISOBATH)} fill={GATE_LIVERY.shallow} />
      {[SHALLOW_ISOBATH, MIDDLE_ISOBATH, DEEP_ISOBATH].map((isobath) => (
        <path
          key={isobath}
          d={isobath}
          fill="none"
          stroke={GATE_LIVERY.isobath}
          strokeWidth={1}
          strokeDasharray="7 4"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  );
}

export function Foreshore() {
  return (
    <svg
      aria-hidden
      className="absolute inset-x-0 bottom-0 h-6 w-full"
      viewBox={`0 0 ${WAVE_VIEW_WIDTH} ${FORESHORE_VIEW_HEIGHT}`}
      preserveAspectRatio="none"
    >
      <path d={areaBelow(FORESHORE_EDGE, FORESHORE_VIEW_HEIGHT)} fill={GATE_LIVERY.foreshore} />
      <path
        d={FORESHORE_EDGE}
        fill="none"
        stroke={GATE_LIVERY.foreshoreLine}
        strokeWidth={1}
        strokeDasharray="1.5 3"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
