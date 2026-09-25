import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/data/**", "src/demo/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/demo", "@/demo/*"],
              message:
                "Demo fixtures are read only through src/data/* hooks so the UI always knows the data origin.",
            },
          ],
        },
      ],
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "public/maplibre/**", "next-env.d.ts"]),
]);
