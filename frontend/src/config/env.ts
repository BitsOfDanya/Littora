import { z } from "zod";

export const SAME_ORIGIN = "/";

const emptyToUndefined = (value: unknown) => (value === "" ? undefined : value);

const publicEnvSchema = z.object({
  apiBaseUrl: z.preprocess(
    emptyToUndefined,
    z.union([z.literal(SAME_ORIGIN), z.url()]).default("http://localhost:8000"),
  ),
  demoFixtures: z.preprocess(
    emptyToUndefined,
    z
      .enum(["true", "false"])
      .default("false")
      .transform((value) => value === "true"),
  ),
});

export const publicEnv = publicEnvSchema.parse({
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
  demoFixtures: process.env.NEXT_PUBLIC_DEMO_FIXTURES,
});
