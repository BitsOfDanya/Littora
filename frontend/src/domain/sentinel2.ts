export const SENTINEL2_BANDS = [
  { id: "B01", name: "Coastal aerosol", centralWavelengthNm: 443, resolutionM: 60 },
  { id: "B02", name: "Blue", centralWavelengthNm: 490, resolutionM: 10 },
  { id: "B03", name: "Green", centralWavelengthNm: 560, resolutionM: 10 },
  { id: "B04", name: "Red", centralWavelengthNm: 665, resolutionM: 10 },
  { id: "B05", name: "Red edge 1", centralWavelengthNm: 705, resolutionM: 20 },
  { id: "B06", name: "Red edge 2", centralWavelengthNm: 740, resolutionM: 20 },
  { id: "B07", name: "Red edge 3", centralWavelengthNm: 783, resolutionM: 20 },
  { id: "B08", name: "NIR", centralWavelengthNm: 842, resolutionM: 10 },
  { id: "B8A", name: "Narrow NIR", centralWavelengthNm: 865, resolutionM: 20 },
  { id: "B09", name: "Water vapour", centralWavelengthNm: 945, resolutionM: 60 },
  { id: "B10", name: "SWIR cirrus", centralWavelengthNm: 1375, resolutionM: 60 },
  { id: "B11", name: "SWIR 1", centralWavelengthNm: 1610, resolutionM: 20 },
  { id: "B12", name: "SWIR 2", centralWavelengthNm: 2190, resolutionM: 20 },
] as const;

export type Sentinel2Band = (typeof SENTINEL2_BANDS)[number];

export type Sentinel2BandId = Sentinel2Band["id"];

export type ProcessingLevel = "L1C" | "L2A";
