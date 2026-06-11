import type { GarminTrackPoint } from "../data/trip";

export const LIVE_HISTORY_URL =
  "https://bitter-silence-3781.max-lindqvist.workers.dev/history";
const TRACK_COLOR = "#2563eb";
const PLANNED_ROUTE_COLOR = "#64748b";

export interface PlannedRouteData {
  points: Array<{ lat: number; lon: number }>;
}

export interface LiveTrackingPageConfig {
  collectionName: string;
  plannedRouteData: PlannedRouteData | null;
  apiUrl?: string;
}

export interface LiveHistoryEntry {
  key?: string;
  data?: {
    lat?: number;
    lon?: number;
    tst?: number;
    alt?: number;
  } | null;
}

export interface LiveTrackingPoint extends GarminTrackPoint {
  distanceMeters: number;
}

export interface ElevationProfileTick {
  val: number;
  y: number;
}

export interface ElevationProfile {
  path: string;
  area: string;
  width: number;
  height: number;
  xMax: number;
  ticks: ElevationProfileTick[];
  padLeft: number;
  padRight: number;
}

export interface LiveTrackingSnapshot {
  points: LiveTrackingPoint[];
  todayDistanceMeters: number;
  elevationProfile: ElevationProfile | null;
  trackerPayload: {
    collections: Array<{
      name: string;
      color: string;
      plannedRouteData: PlannedRouteData | null;
      activities: Array<{
        color: string;
        routeData:
          | {
              status: "ok";
              points: LiveTrackingPoint[];
              summary: {
                pointCount: number;
                isActive: boolean;
                lastReportedTime?: string;
                totalDistanceMeters?: number;
              };
            }
          | null;
        notes: string;
        plannedRouteData: null;
      }>;
    }>;
  };
}

export function serializeDataForScript(value: unknown): string {
  const json = JSON.stringify(value ?? {});
  return json
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026");
}

export function formatDistance(meters: number): string {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }
  return `${Math.round(meters)} m`;
}

export function formatTime(isoTime?: string): string {
  if (!isoTime) {
    return "-";
  }
  return new Date(isoTime).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function buildLiveTrackingSnapshot(
  config: LiveTrackingPageConfig,
  history: LiveHistoryEntry[],
): LiveTrackingSnapshot {
  const points = buildLivePoints(history);
  const lastPoint = points.at(-1);

  return {
    points,
    todayDistanceMeters: calculateTodayDistance(points),
    elevationProfile: buildElevationProfile(points),
    trackerPayload: {
      collections: [
        {
          name: config.collectionName,
          color: TRACK_COLOR,
          plannedRouteData: config.plannedRouteData,
          activities: [
            {
              color: TRACK_COLOR,
              routeData:
                points.length > 0
                  ? {
                      status: "ok",
                      points,
                      summary: {
                        pointCount: points.length,
                        isActive: true,
                        lastReportedTime: lastPoint?.time,
                        totalDistanceMeters: lastPoint?.distanceMeters,
                      },
                    }
                  : null,
              notes: "Live Progress",
              plannedRouteData: null,
            },
          ],
        },
      ],
    },
  };
}

export function emptyLiveTrackingSnapshot(
  config: LiveTrackingPageConfig,
): LiveTrackingSnapshot {
  return buildLiveTrackingSnapshot(config, []);
}

export async function fetchLiveTrackingSnapshot(
  config: LiveTrackingPageConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<LiveTrackingSnapshot> {
  const response = await fetchImpl(config.apiUrl ?? LIVE_HISTORY_URL, {
    headers: {
      accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Live tracking request failed with ${response.status}`);
  }

  const history = (await response.json()) as unknown;
  if (!Array.isArray(history)) {
    throw new Error("Live tracking API returned a non-array payload");
  }

  return buildLiveTrackingSnapshot(config, history as LiveHistoryEntry[]);
}

export function renderElevationProfileMarkup(
  elevationProfile: ElevationProfile | null,
): string {
  if (!elevationProfile) {
    return '<p class="text-sm text-slate-500">No elevation data yet.</p>';
  }

  const tickMarkup = elevationProfile.ticks
    .map(
      (tick) => `
        <g>
          <line x1="${elevationProfile.padLeft}" y1="${tick.y}" x2="${elevationProfile.width - elevationProfile.padRight}" y2="${tick.y}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="4 4" />
          <text x="${elevationProfile.padLeft - 8}" y="${tick.y}" text-anchor="end" dominant-baseline="middle" fill="#94a3b8" font-weight="bold" style="font-size: 10px; font-family: ui-sans-serif, system-ui, sans-serif;">${tick.val}m</text>
        </g>
      `,
    )
    .join("");

  return `
    <div class="w-full">
      <svg viewBox="0 0 ${elevationProfile.width} ${elevationProfile.height}" class="w-full h-auto" preserveAspectRatio="none">
        <defs>
          <linearGradient id="elev-grad" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#fc4c02" stop-opacity="0.2" />
            <stop offset="100%" stop-color="#fc4c02" stop-opacity="0" />
          </linearGradient>
        </defs>
        ${tickMarkup}
        <path d="${elevationProfile.area}" fill="url(#elev-grad)" />
        <path d="${elevationProfile.path}" fill="none" stroke="#fc4c02" stroke-width="2" stroke-linejoin="round" />
      </svg>
    </div>
    <div class="flex justify-between mt-2 pl-10 text-[10px] font-bold text-slate-400 uppercase">
      <span>Start</span>
      <span>${Math.round(elevationProfile.xMax / 1000)} km</span>
    </div>
  `;
}

export function setupLiveTrackingPage(config: LiveTrackingPageConfig): void {
  const refreshButton = document.getElementById(
    "refresh-button",
  ) as HTMLButtonElement | null;
  const refreshIcon = document.getElementById("refresh-icon");

  if (!refreshButton || !refreshIcon) {
    console.error("Live tracking: refresh button or icon not found");
    return;
  }
  if (refreshButton.dataset.liveTrackingInitialized === "true") {
    console.log("Live tracking: already initialized");
    return;
  }
  refreshButton.dataset.liveTrackingInitialized = "true";

  const refresh = async (): Promise<void> => {
    console.log("Live tracking: starting refresh...");
    setRefreshLoadingState(true);
    setRefreshStatus("Refreshing live data…", "loading");

    try {
      const snapshot = await fetchLiveTrackingSnapshot(config, window.fetch.bind(window));
      console.log("Live tracking: fetched snapshot with", snapshot.points.length, "points");
      await renderSnapshot(config, snapshot);
      console.log("Live tracking: rendered snapshot successfully");
      setRefreshStatus(
        `Updated ${formatTime(new Date().toISOString())}`,
        "success",
      );
    } catch (error) {
      console.error("Live tracking refresh failed:", error);
      setRefreshStatus(
        "Refresh failed. Showing the last available data.",
        "error",
      );
    } finally {
      setRefreshLoadingState(false);
    }
  };

  refreshButton.addEventListener("click", () => {
    void refresh();
  });

  console.log("Live tracking: triggering initial refresh");
  void refresh();
}

function buildLivePoints(history: LiveHistoryEntry[]): LiveTrackingPoint[] {
  const validEntries = history
    .map((entry) => entry.data ?? null)
    .filter(
      (
        entry,
      ): entry is {
        lat: number;
        lon: number;
        tst: number;
        alt?: number;
      } =>
        entry !== null &&
        typeof entry.lat === "number" &&
        typeof entry.lon === "number" &&
        typeof entry.tst === "number" &&
        entry.lat !== 0 &&
        entry.lon !== 0,
    )
    .sort((a, b) => a.tst - b.tst);

  let totalDistance = 0;

  return validEntries.map((entry, index) => {
    if (index > 0) {
      const previous = validEntries[index - 1];
      totalDistance += calculateDistance(
        previous.lat,
        previous.lon,
        entry.lat,
        entry.lon,
      );
    }

    return {
      lat: entry.lat,
      lon: entry.lon,
      elevation: entry.alt,
      distanceMeters: totalDistance,
      time: new Date(entry.tst * 1000).toISOString(),
    };
  });
}

function calculateTodayDistance(points: LiveTrackingPoint[]): number {
  if (points.length < 2) {
    return 0;
  }

  const lastPoint = points.at(-1);
  if (!lastPoint?.time) {
    return 0;
  }

  const lastDate = new Date(lastPoint.time).toDateString();
  const pointsToday = points.filter(
    (point) => point.time && new Date(point.time).toDateString() === lastDate,
  );
  if (pointsToday.length < 2) {
    return 0;
  }

  return (
    pointsToday.at(-1)!.distanceMeters - pointsToday[0]!.distanceMeters
  );
}

function buildElevationProfile(
  points: LiveTrackingPoint[],
): ElevationProfile | null {
  const data = points.filter(
    (point): point is LiveTrackingPoint & { elevation: number } =>
      typeof point.elevation === "number" &&
      typeof point.distanceMeters === "number",
  );
  if (data.length < 2) {
    return null;
  }

  const width = 800;
  const height = 150;
  const padLeft = 40;
  const padRight = 20;
  const padTop = 10;
  const padBottom = 20;
  const xMax = data.at(-1)?.distanceMeters ?? 0;
  const rawYMin = Math.min(...data.map((point) => point.elevation));
  const rawYMax = Math.max(...data.map((point) => point.elevation));
  const yMin = Math.floor(rawYMin / 10) * 10 - 10;
  const yMax = Math.ceil(rawYMax / 10) * 10 + 10;
  const yRange = Math.max(yMax - yMin, 1);
  const xRange = Math.max(xMax, 1);

  const scaleX = (x: number): number =>
    padLeft + (x / xRange) * (width - padLeft - padRight);
  const scaleY = (y: number): number =>
    height -
    padBottom -
    ((y - yMin) / yRange) * (height - padTop - padBottom);

  const path = data
    .map((point, index) =>
      `${index === 0 ? "M" : "L"} ${scaleX(point.distanceMeters)} ${scaleY(point.elevation)}`,
    )
    .join(" ");
  const area =
    path +
    ` L ${scaleX(xMax)} ${height - padBottom} L ${scaleX(0)} ${height - padBottom} Z`;
  const tickCount = 4;
  const ticks = Array.from({ length: tickCount }, (_, index) => {
    const val = yMin + (index * yRange) / (tickCount - 1);
    return { val: Math.round(val), y: scaleY(val) };
  });

  return {
    path,
    area,
    width,
    height,
    xMax,
    ticks,
    padLeft,
    padRight,
  };
}

async function renderSnapshot(
  config: LiveTrackingPageConfig,
  snapshot: LiveTrackingSnapshot,
): Promise<void> {
  const actualTracks =
    snapshot.points.length > 0
      ? [
          {
            name: "Live Progress",
            points: snapshot.points,
            color: TRACK_COLOR,
          },
        ]
      : [];
  const plannedRoutes = config.plannedRouteData
    ? [
        {
          name: `${config.collectionName} (Planned)`,
          points: config.plannedRouteData.points,
          color: PLANNED_ROUTE_COLOR,
          isPlanned: true,
        },
      ]
    : [];

  const { setupMap } = await import("./map-renderer");
  setupMap({
    containerId: "collection-map",
    tracks: actualTracks,
    plannedRoutes,
  });

  setText("live-total-distance", formatDistance(snapshot.points.at(-1)?.distanceMeters ?? 0));
  setText("live-today-distance", formatDistance(snapshot.todayDistanceMeters));
  setText("live-last-point", formatTime(snapshot.points.at(-1)?.time));
  setText("live-track-points", String(snapshot.points.length));

  const elevationContainer = document.getElementById("elevation-profile-content");
  if (elevationContainer) {
    elevationContainer.innerHTML = renderElevationProfileMarkup(
      snapshot.elevationProfile,
    );
  }
}

function setText(id: string, value: string): void {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function setRefreshLoadingState(isLoading: boolean): void {
  const refreshButton = document.getElementById(
    "refresh-button",
  ) as HTMLButtonElement | null;
  const refreshIcon = document.getElementById("refresh-icon");
  if (!refreshButton || !refreshIcon) {
    return;
  }

  refreshButton.disabled = isLoading;
  refreshButton.classList.toggle("opacity-75", isLoading);
  refreshButton.classList.toggle("cursor-wait", isLoading);
  refreshIcon.classList.toggle("animate-spin", isLoading);
}

function setRefreshStatus(
  message: string,
  tone: "loading" | "success" | "error",
): void {
  const status = document.getElementById("refresh-status");
  if (!status) {
    return;
  }

  status.textContent = message;
  status.className = "mt-2 text-sm";

  if (tone === "loading") {
    status.classList.add("text-slate-500");
    return;
  }
  if (tone === "success") {
    status.classList.add("text-emerald-600");
    return;
  }

  status.classList.add("text-red-600");
}

function calculateDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const earthRadiusMeters = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusMeters * c;
}
