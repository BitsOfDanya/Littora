import type { Metadata, Viewport } from "next";
import { SITE } from "@/config/site";
import { chartFont, dataFont, uiFont } from "./fonts";
import { Providers } from "./providers";
import { ThemeScript } from "./theme-script";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: SITE.product, template: `%s · ${SITE.product}` },
  description: SITE.claim,
};

export const viewport: Viewport = {
  themeColor: "#0a0e11",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ru"
      data-theme="night"
      className={`${uiFont.variable} ${dataFont.variable} ${chartFont.variable}`}
      suppressHydrationWarning
    >
      <head>
        <ThemeScript />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
