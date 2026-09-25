"use client";

import { AoiSelector } from "./aoi-selector";
import { Brand } from "./brand";
import { CommandBox } from "./command-box";
import { DemoSwitch } from "./demo-switch";
import { ModeTabs } from "./mode-tabs";
import { ThemeSeg, ThemeToggleButton } from "./theme-switch";
import { UtcClock } from "./utc-clock";

export function TopBar() {
  return (
    <header className="flex h-full min-w-0 items-stretch border-b border-line-hairline bg-surface-panel">
      <Brand />
      <AoiSelector />
      <div className="hidden lg:block">
        <ModeTabs variant="bar" />
      </div>
      <div className="ml-auto hidden shrink-0 items-center gap-1.5 pr-3 pl-2 md:flex">
        <DemoSwitch />
        <CommandBox />
        <span className="hidden xl:inline-flex">
          <UtcClock />
        </span>
        <ThemeSeg />
      </div>
      <div className="flex shrink-0 items-center md:hidden">
        <CommandBox variant="phone" />
        <ThemeToggleButton />
      </div>
    </header>
  );
}
