"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

const MapView = dynamic(() => import("./map-view"), { ssr: false });

export function MapStage(props: ComponentProps<typeof MapView>) {
  return (
    <div className="absolute inset-0">
      <MapView {...props} />
    </div>
  );
}
