export interface CollectionActivity {
  garminLivetrackUrl?: string | null;
  stravaActivityId?: string | null;
  strava_id?: [number, boolean] | null;
  notes?: string;
  routeGpxFile?: string | string[] | null;
}

export interface CollectionMetadata {
  activities?: CollectionActivity[];
  routeGpxFile?: string | string[] | null;
  garminLivetrackUrl?: string | null;
}
