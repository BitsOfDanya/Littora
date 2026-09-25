import type { SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 16, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden
      focusable={false}
      {...props}
    >
      {children}
    </svg>
  );
}

export const IconChevronDown = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 6l4 4 4-4" />
  </Icon>
);
export const IconChevronUp = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 10l4-4 4 4" />
  </Icon>
);
export const IconChevronLeft = (props: IconProps) => (
  <Icon {...props}>
    <path d="M10 4L6 8l4 4" />
  </Icon>
);
export const IconChevronRight = (props: IconProps) => (
  <Icon {...props}>
    <path d="M6 4l4 4-4 4" />
  </Icon>
);
export const IconArrowRight = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2.5 8h10M9 4.5L12.5 8 9 11.5" />
  </Icon>
);
export const IconClose = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Icon>
);
export const IconExit = (props: IconProps) => (
  <Icon {...props}>
    <path d="M6.5 2.5h-4v11h4M10.5 5l3 3-3 3M6 8h7.5" />
  </Icon>
);
export const IconGrip = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 6.5h8M4 9.5h8" />
  </Icon>
);

export const IconPlus = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 3v10M3 8h10" />
  </Icon>
);
export const IconMinus = (props: IconProps) => (
  <Icon {...props}>
    <path d="M3 8h10" />
  </Icon>
);
export const IconNorth = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 1.8l3.4 11.4L8 10.6l-3.4 2.6L8 1.8z" />
  </Icon>
);
export const IconFitArea = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2 5.5V2h3.5M10.5 2H14v3.5M14 10.5V14h-3.5M5.5 14H2v-3.5" />
  </Icon>
);
export const IconGraticule = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5.5 1.5v13M10.5 1.5v13M1.5 5.5h13M1.5 10.5h13" />
  </Icon>
);
export const IconLayers = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 2l6 3.2-6 3.2-6-3.2L8 2z" />
    <path d="M2 8.4l6 3.2 6-3.2" />
    <path d="M2 11.2l6 3.2 6-3.2" />
  </Icon>
);
export const IconProbe = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2 2h12v12H2z" />
    <path d="M8 4.5v7M4.5 8h7" />
  </Icon>
);
export const IconRuler = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2 11l9-9 3 3-9 9-3-3z" />
    <path d="M5 8l1.5 1.5M7 6l1 1M9 4l1.5 1.5" />
  </Icon>
);

export const IconPlay = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5 3.5v9l7-4.5-7-4.5z" />
  </Icon>
);
export const IconPause = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5.5 3.5v9M10.5 3.5v9" />
  </Icon>
);
export const IconStepBack = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 3.5v9M12 3.5L6.5 8l5.5 4.5" />
  </Icon>
);
export const IconStepForward = (props: IconProps) => (
  <Icon {...props}>
    <path d="M12 3.5v9M4 3.5L9.5 8 4 12.5" />
  </Icon>
);
export const IconNextUsable = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2.5 4v8M2.5 8h9.5M9 4.8L12.2 8 9 11.2" />
    <path d="M14 4v8" />
  </Icon>
);
export const IconSwap = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2.5 5.5h10M10 3l2.5 2.5L10 8M13.5 10.5h-10M6 8l-2.5 2.5L6 13" />
  </Icon>
);
export const IconSwipe = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2 2.5h12v11H2z" />
    <path d="M8 1v14" />
    <path d="M6.5 6.5L5 8l1.5 1.5M9.5 6.5L11 8 9.5 9.5" />
  </Icon>
);
export const IconOpacity = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2 2.5h12v11H2z" />
    <path d="M8 2.5v11M8 5l6-2.5M8 9l6-3M8 13l6-3" />
  </Icon>
);
export const IconLens = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="8" cy="8" r="5.5" />
    <path d="M8 5v6M5 8h6" />
  </Icon>
);

export const IconRing = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="8" cy="8" r="3.5" />
  </Icon>
);
export const IconCaution = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 2l6.5 11.5h-13L8 2z" />
    <path d="M8 6.5v3.5M8 11.5v.6" />
  </Icon>
);
export const IconAlarm = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5.5 1.5h5l4 4v5l-4 4h-5l-4-4v-5l4-4z" />
    <path d="M8 5v3.8M8 10.6v.6" />
  </Icon>
);
export const IconDiamond = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 2l6 6-6 6-6-6 6-6z" />
  </Icon>
);
export const IconSocket = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2.5 3.5h11v9h-11z" strokeDasharray="2 1.6" />
    <path d="M6 7v2M10 7v2" />
  </Icon>
);
export const IconCheck = (props: IconProps) => (
  <Icon {...props}>
    <path d="M3 8.5l3 3 7-7" />
  </Icon>
);
export const IconHatch = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2 2h12v12H2z" />
    <path d="M2 8l6-6M2 14L14 2M8 14l6-6" />
  </Icon>
);

export const IconSearch = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.5 10.5L14 14" />
  </Icon>
);
export const IconCopy = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5.5 5.5h8v8h-8z" />
    <path d="M10.5 5.5v-3h-8v8h3" />
  </Icon>
);
export const IconDownload = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 2v8M4.5 6.5L8 10l3.5-3.5M2.5 13.5h11" />
  </Icon>
);
export const IconPin = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 14s4.5-4.2 4.5-7.5a4.5 4.5 0 0 0-9 0C3.5 9.8 8 14 8 14z" />
    <circle cx="8" cy="6.5" r="1.5" />
  </Icon>
);
export const IconFlag = (props: IconProps) => (
  <Icon {...props}>
    <path d="M3.5 14.5V2M3.5 2.5h8.5l-2 3 2 3H3.5" />
  </Icon>
);
export const IconLink = (props: IconProps) => (
  <Icon {...props}>
    <path d="M6.5 9.5l3-3M7 4.5l1-1a2.8 2.8 0 0 1 4 4l-1 1M9 11.5l-1 1a2.8 2.8 0 0 1-4-4l1-1" />
  </Icon>
);
export const IconParticles = (props: IconProps) => (
  <Icon {...props}>
    <path d="M1.5 5c2-1.5 4-1.5 6 0s4 1.5 6 0" strokeDasharray="1.5 1.8" />
    <path d="M1.5 9c2-1.5 4-1.5 6 0s4 1.5 6 0" />
    <path d="M1.5 13c2-1.5 4-1.5 6 0s4 1.5 6 0" strokeDasharray="1.5 1.8" />
  </Icon>
);
export const IconAnchor = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="8" cy="3.5" r="1.5" />
    <path d="M8 5v9M5 7.5h6M2.5 10c.5 2.5 3 4 5.5 4s5-1.5 5.5-4" />
  </Icon>
);

export const IconSun = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M13 3l-1.4 1.4M4.4 11.6L3 13" />
  </Icon>
);
export const IconMoon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M13 9.5A5.5 5.5 0 1 1 6.5 3a4.5 4.5 0 0 0 6.5 6.5z" />
  </Icon>
);
export const IconInfo = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 7v4.5M8 4.6v.8" />
  </Icon>
);
export const IconKeyboard = (props: IconProps) => (
  <Icon {...props}>
    <path d="M1.5 4h13v8h-13z" />
    <path d="M4 6.5h.5M6.5 6.5H7M9 6.5h.5M11.5 6.5h.5M4.5 9.5h7" />
  </Icon>
);
export const IconSignal = (props: IconProps) => (
  <Icon {...props}>
    <path d="M2.5 13.5v-2M6 13.5v-5M9.5 13.5v-8M13 13.5V2.5" />
  </Icon>
);

export const ModeIcons = {
  monitor: (props: IconProps) => (
    <Icon {...props}>
      <path d="M2 2.5h12v11H2z" />
      <path d="M2 5h2.5V2.5" />
      <path d="M4.5 10.5c1.5-.8 2.2-3 3.6-3s2 1.8 3.4 1" />
    </Icon>
  ),
  timeline: (props: IconProps) => (
    <Icon {...props}>
      <path d="M1.5 13h13" />
      <path d="M3 10h2v3M7 7h2v6M11 4h2v9" />
    </Icon>
  ),
  forecast: (props: IconProps) => (
    <Icon {...props}>
      <path d="M2.5 11.5L13 4M2.5 11.5l10 1.5M2.5 11.5L10.5 2" strokeDasharray="2 1.6" />
      <circle cx="2.5" cy="11.5" r="1.3" />
    </Icon>
  ),
  survey: (props: IconProps) => (
    <Icon {...props}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M7 5.8L8.4 5v6" />
    </Icon>
  ),
  models: (props: IconProps) => (
    <Icon {...props}>
      <path d="M2 2h12v12H2zM6 2v12M10 2v12M2 6h12M2 10h12" />
    </Icon>
  ),
} as const;
