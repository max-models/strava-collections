export interface CollectionActivity {
  garminLivetrackUrl?: string | null;
  stravaActivityId?: string | null;
  notes?: string;
  routeGpxFile?: string | null;
}

export interface Collection {
  name: string;
  routeGpxFile?: string | null;
  activities: CollectionActivity[];
}

export interface TripData {
  collections: Collection[];
}
