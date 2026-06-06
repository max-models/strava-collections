export interface CollectionActivity {
  garminLivetrackUrl?: string | null;
  stravaActivityId?: string | null;
  notes?: string;
  routeGpxFile?: string | string[] | null;
}

export interface Collection {
  name: string;
  routeGpxFile?: string | string[] | null;
  activities: CollectionActivity[];
}

export interface TripData {
  collections: Collection[];
}
