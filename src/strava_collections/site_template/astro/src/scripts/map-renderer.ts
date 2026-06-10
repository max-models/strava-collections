import Leaflet from 'leaflet';

export interface TrackPoint {
  lat: number;
  lon: number;
  time?: string;
  elevation?: number;
  heartRateBeatsPerMin?: number;
  cadenceCyclesPerMin?: number;
  powerWatts?: number;
}

export interface MapTrack {
  points: TrackPoint[];
  color: string;
  name: string;
  isPlanned?: boolean;
}

export interface MapOptions {
  containerId: string;
  tracks: MapTrack[];
  plannedRoutes?: MapTrack[];
}

export function setupMap(options: MapOptions) {
  const { containerId, tracks, plannedRoutes = [] } = options;
  const container = document.getElementById(containerId);
  if (!container) return null;

  const map = Leaflet.map(container, {
    zoomControl: true,
    scrollWheelZoom: true,
  });

  Leaflet.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  const bounds = Leaflet.latLngBounds([]);

  // Draw planned routes first (background)
  plannedRoutes.forEach(route => {
    if (route.points.length < 2) return;
    const latLngs = route.points.map(p => [p.lat, p.lon] as [number, number]);
    const poly = Leaflet.polyline(latLngs, {
      color: "#64748b",
      weight: 6,
      opacity: 0.4,
    }).addTo(map);
    Leaflet.polyline(latLngs, {
      color: "#ffffff",
      weight: 2,
      opacity: 0.8,
      dashArray: "12 12",
    }).addTo(map);
    bounds.extend(poly.getBounds());
  });

  // Draw actual tracks
  tracks.forEach(track => {
    if (track.points.length === 0) return;
    const latLngs = track.points.map(p => [p.lat, p.lon] as [number, number]);
    const poly = Leaflet.polyline(latLngs, {
      color: track.color,
      weight: 5,
      opacity: 0.9,
    }).addTo(map);

    bounds.extend(poly.getBounds());
  });

  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 18 });
  }

  return map;
}
