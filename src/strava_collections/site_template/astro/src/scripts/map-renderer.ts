import Leaflet from "leaflet";

const mapInstances = new WeakMap<HTMLElement, Leaflet.Map>();

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
  places?: Array<{ name: string; lat: number; lon: number }>;
}

function haversineDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function isPlaceNearAnyTrack(
  place: { lat: number; lon: number },
  tracks: MapTrack[],
): boolean {
  const threshold = 20.0; // km
  for (const track of tracks) {
    for (const p of track.points) {
      if (haversineDistance(place.lat, place.lon, p.lat, p.lon) <= threshold) {
        return true;
      }
    }
  }
  return false;
}

export function setupMap(options: MapOptions) {
  const { containerId, tracks, plannedRoutes = [], places = [] } = options;
  let container = document.getElementById(containerId);
  if (!container) return null;

  const existingMap = mapInstances.get(container);
  if (existingMap) {
    existingMap.remove();
    mapInstances.delete(container);
  } else if (
    "_leaflet_id" in container ||
    container.classList.contains("leaflet-container")
  ) {
    const replacement = container.cloneNode(false) as HTMLElement;
    container.replaceWith(replacement);
    container = replacement;
  }

  container.innerHTML = "";

  const map = Leaflet.map(container, {
    zoomControl: true,
    scrollWheelZoom: true,
  });

  // ... (tile layers same as before)
  const osmLayer = Leaflet.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    },
  );

  const topoLayer = Leaflet.tileLayer(
    "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    {
      attribution:
        'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)',
      maxZoom: 17,
    },
  );

  const satelliteLayer = Leaflet.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      attribution:
        "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
      maxZoom: 19,
    },
  );

  const cycleLayer = Leaflet.tileLayer(
    "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
    {
      attribution:
        '<a href="https://github.com/cyclosm/cyclosm-cartocss-style/releases" title="CyclOSM - Open Bicycle render">CyclOSM</a> | Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 20,
    },
  );

  const humanitarianLayer = Leaflet.tileLayer(
    "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
    {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, Tiles style by <a href="https://www.hotosm.org/" target="_blank">Humanitarian OpenStreetMap Team</a> hosted by <a href="https://openstreetmap.fr/" target="_blank">OpenStreetMap France</a>',
      maxZoom: 19,
    },
  );

  const voyagerLayer = Leaflet.tileLayer(
    "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 20,
    },
  );

  const darkLayer = Leaflet.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 20,
    },
  );

  // Add default layer
  osmLayer.addTo(map);

  // Add layer control positioned below zoom controls
  const baseMaps = {
    OpenStreetMap: osmLayer,
    Topographic: topoLayer,
    Satellite: satelliteLayer,
    Cycling: cycleLayer,
    Humanitarian: humanitarianLayer,
    Voyager: voyagerLayer,
    "Dark Matter": darkLayer,
  };

  Leaflet.control.layers(baseMaps, {}, { position: "topleft" }).addTo(map);

  const bounds = Leaflet.latLngBounds([]);

  // Draw planned routes first (background) - each route separately
  plannedRoutes.forEach((route) => {
    if (route.points.length < 2) return;
    const latLngs = route.points.map((p) => [p.lat, p.lon] as [number, number]);
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
  tracks.forEach((track) => {
    if (track.points.length === 0) return;
    const latLngs = track.points.map((p) => [p.lat, p.lon] as [number, number]);
    const poly = Leaflet.polyline(latLngs, {
      color: track.color,
      weight: 5,
      opacity: 0.9,
    }).addTo(map);

    bounds.extend(poly.getBounds());
  });

  // Draw places
  places.forEach((place) => {
    const isNear = isPlaceNearAnyTrack(place, tracks);
    const color = isNear ? "#10b981" : "#ef4444"; // emerald-500 or red-500

    const marker = Leaflet.circleMarker([place.lat, place.lon], {
      radius: 5,
      fillColor: color,
      color: "#ffffff",
      weight: 2,
      opacity: 1,
      fillOpacity: 0.8,
    }).addTo(map);

    marker.bindPopup(
      `<b>${place.name}</b><br>Lat: ${place.lat.toFixed(4)}, Lon: ${place.lon.toFixed(4)}`,
    );
    bounds.extend([place.lat, place.lon]);
  });

  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 18 });
  }

  mapInstances.set(container, map);
  return map;
}
