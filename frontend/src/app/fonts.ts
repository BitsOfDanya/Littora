import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";

export const uiFont = IBM_Plex_Sans({
  subsets: ["latin", "cyrillic"],
  axes: ["wdth"],
  variable: "--font-ui",
  display: "swap",
});

export const dataFont = IBM_Plex_Mono({
  subsets: ["latin", "cyrillic"],
  weight: ["400", "500", "600"],
  variable: "--font-data",
  display: "swap",
});

export const chartFont = Source_Serif_4({
  subsets: ["latin", "cyrillic"],
  style: ["italic", "normal"],
  axes: ["opsz"],
  variable: "--font-chart",
  display: "swap",
});
