export type DatasetRole = "training" | "validation" | "calibration" | "reference";

export type DatasetReference = {
  id: string;
  name: string;
  fullName: string;
  role: DatasetRole;
  sensor: string;
  labels: string;
  volume: string;
  license: string;
  doi: string;
  period: string;
  coverage: string;
  useInLittora: string;
};
