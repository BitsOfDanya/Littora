export type DemoUnavailable = "disabled" | "other-aoi" | "not-provided";

export type Sourced<T> =
  | { origin: "api"; data: T }
  | { origin: "demo"; data: T }
  | { origin: "none"; demo: DemoUnavailable };
