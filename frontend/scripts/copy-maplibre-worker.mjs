import { copyFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const sourceDir = path.dirname(require.resolve("maplibre-gl/dist/maplibre-gl.css"));
const targetDir = path.resolve(import.meta.dirname, "../public/maplibre");
const files = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

await mkdir(targetDir, { recursive: true });
await Promise.all(
  files.map((file) => copyFile(path.join(sourceDir, file), path.join(targetDir, file))),
);
