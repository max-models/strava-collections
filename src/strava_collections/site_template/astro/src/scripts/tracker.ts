interface GarminTrackPoint {
  lat: number;
  lon: number;
  time?: string;
  distanceMeters?: number;
  durationSecs?: number;
  elevation?: number;
  speedMetersPerSec?: number;
  heartRateBeatsPerMin?: number;
  cadenceCyclesPerMin?: number;
  powerWatts?: number;
}

interface GarminRouteSummary {
  totalDistanceMeters?: number;
  totalDurationSecs?: number;
  lastReportedTime?: string;
  pointCount: number;
  isActive: boolean;
}

interface GarminRouteOk {
  status: "ok";
  points: GarminTrackPoint[];
  summary: GarminRouteSummary;
}

interface GarminRouteEmpty {
  status: "empty";
}

interface GarminRouteError {
  status: "error";
}

type GarminRouteData = GarminRouteOk | GarminRouteEmpty | GarminRouteError;

interface PlannedRouteData {
  points: Array<{ lat: number; lon: number }>;
}

interface TrackerActivity {
  color: string;
  garminLivetrackUrl: string | null;
  stravaActivityId: string | null;
  notes: string | null;
  routeData: GarminRouteData | null;
  plannedRouteData: PlannedRouteData | null;
}

interface TrackerCollection {
  name: string;
  color: string;
  plannedRouteData: PlannedRouteData | null;
  activities: TrackerActivity[];
}

interface TrackerPayload {
  collections: TrackerCollection[];
}

interface RouteEntry {
  collectionIndex: number;
  collectionName: string;
  activityLabel: string;
  color: string;
  activityIndex: number;
  garminLivetrackUrl: string | null;
  stravaActivityId: string | null;
  notes: string | null;
  routeData: GarminRouteOk;
  plannedRouteData: PlannedRouteData | null;
}

interface ChartSeriesPoint {
  x: number;
  displayX?: number;
  y: number;
}

interface ChartSeries {
  color: string;
  label: string;
  xTotal: number;
  points: ChartSeriesPoint[];
}

interface GraphMetricConfig {
  key: "elevation" | "speed" | "heartRate" | "power" | "cadence";
  title: string;
  xLabel: string;
  yLabel: string;
  baselineAtZero: boolean;
  xFormatter: (v: number) => string;
  yFormatter: (v: number) => string;
  selectPoint: (point: GarminTrackPoint, prev?: GarminTrackPoint) => ChartSeriesPoint | null;
}

interface LeafletState {
  map: import("leaflet").Map;
  tileLayer: import("leaflet").TileLayer;
  collectionGroups: Map<number, import("leaflet").FeatureGroup>;
}

let leafletState: LeafletState | null = null;
let gpxDownloadUrls: string[] = [];
let visibleCollections: Set<number> = new Set();
let allRouteEntries: RouteEntry[] = [];
let trackerCollections: TrackerCollection[] = [];
let activeCollectionIndex: number | null = null;
let activeGraphMetric: GraphMetricConfig["key"] = "speed";

export async function setupTripTracker(payload: TrackerPayload): Promise<void> {
  const { collections } = payload;
  trackerCollections = collections;

  allRouteEntries = collections.flatMap((col, ci) =>
    col.activities
      .map((activity, ai) => ({ col, ci, ai, activity }))
      .filter(
        ({ activity }): activity is typeof activity & { routeData: GarminRouteOk } =>
          activity.routeData?.status === "ok" && activity.routeData.points.length > 0,
      )
      .map(({ col, ci, ai, activity }) => ({
        collectionIndex: ci,
        collectionName: col.name,
        activityLabel: `${col.name} #${ai + 1}`,
        color: activity.color,
        activityIndex: ai,
        garminLivetrackUrl: activity.garminLivetrackUrl,
        stravaActivityId: activity.stravaActivityId,
        notes: activity.notes,
        routeData: activity.routeData as GarminRouteOk,
        plannedRouteData: activity.plannedRouteData,
      })),
  );

  const firstCollectionWithRoute = collections.findIndex(
    (col, ci) =>
      allRouteEntries.some((entry) => entry.collectionIndex === ci) ||
      col.plannedRouteData ||
      col.activities.some((a) => a.plannedRouteData),
  );
  activeCollectionIndex =
    firstCollectionWithRoute >= 0 ? firstCollectionWithRoute : collections.length > 0 ? 0 : null;
  visibleCollections =
    activeCollectionIndex === null ? new Set<number>() : new Set<number>([activeCollectionIndex]);

  const mapShell = getElement<HTMLDivElement>("map-shell");
  const placeholder = getElement<HTMLDivElement>("map-placeholder");
  const mapElement = getElement<HTMLDivElement>("main-map");

  if (mapShell && placeholder && mapElement) {
    await renderMap({ mapShell, placeholder, mapElement, collections });
  }

  renderCollectionControls(collections);
  renderActivityList(collections, activeCollectionIndex);
  revokeGpxUrls();
}

async function renderMap(options: {
  mapShell: HTMLDivElement;
  placeholder: HTMLDivElement;
  mapElement: HTMLDivElement;
  collections: TrackerCollection[];
}): Promise<void> {
  const { mapShell, placeholder, mapElement, collections } = options;

  mapShell.classList.add("hidden");
  placeholder.classList.remove("hidden");
  hideMapStats();
  hideLiveStats();
  hideGraphs();

  const anyPlanned = collections.some((col, ci) => visibleCollections.has(ci) && (col.plannedRouteData || col.activities.some(a => a.plannedRouteData)));
  const allVisible = getVisibleRouteEntries();

  if (allVisible.length === 0 && !anyPlanned) {
    placeholder.innerHTML = buildPlaceholderCopy(collections);
    return;
  }

  const Leaflet = await import("leaflet");

  if (!leafletState) {
    const map = Leaflet.map(mapElement, {
      zoomControl: true,
      scrollWheelZoom: true,
    });

    Leaflet.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    const collectionGroups = new Map<number, import("leaflet").FeatureGroup>();

    leafletState = {
      map,
      tileLayer: Leaflet.tileLayer(""),
      collectionGroups,
    };
  }

  // rebuild collection groups
  leafletState.collectionGroups.forEach((group) => group.remove());
  leafletState.collectionGroups.clear();

  const bounds = Leaflet.latLngBounds([]);

  for (let ci = 0; ci < collections.length; ci++) {
    const col = collections[ci];
    let group = leafletState.collectionGroups.get(ci);
    if (!group) {
      group = Leaflet.featureGroup().addTo(leafletState.map);
      leafletState.collectionGroups.set(ci, group);
    }

    if (col.plannedRouteData && col.plannedRouteData.points.length > 1) {
      const plannedLatLngs = col.plannedRouteData.points.map((p) => [p.lat, p.lon] as [number, number]);
      const poly = Leaflet.polyline(plannedLatLngs, {
        color: "#64748b",
        weight: 6,
        opacity: 0.4,
      }).addTo(group);
      Leaflet.polyline(plannedLatLngs, {
        color: "#ffffff",
        weight: 2,
        opacity: 0.8,
        dashArray: "12 12",
      }).addTo(group);
      if (visibleCollections.has(ci)) {
        bounds.extend(poly.getBounds());
      }
    }

    for (let ai = 0; ai < col.activities.length; ai++) {
      const activity = col.activities[ai];

      if (activity.plannedRouteData && activity.plannedRouteData.points.length > 1) {
        const plannedLatLngs = activity.plannedRouteData.points.map((p) => [p.lat, p.lon] as [number, number]);
        const poly = Leaflet.polyline(plannedLatLngs, {
          color: "#64748b",
          weight: 6,
          opacity: 0.4,
        }).addTo(group);
        Leaflet.polyline(plannedLatLngs, {
          color: "#ffffff",
          weight: 2,
          opacity: 0.8,
          dashArray: "12 12",
        }).addTo(group);
        if (visibleCollections.has(ci)) {
          bounds.extend(poly.getBounds());
        }
      }

      if (activity.routeData?.status === "ok" && activity.routeData.points.length > 0) {
        const latLngs = activity.routeData.points.map((p) => [p.lat, p.lon] as [number, number]);
        const poly = Leaflet.polyline(latLngs, { color: activity.color, weight: 5, opacity: 0.9 }).addTo(group);

        const lastLatLng = latLngs.at(-1);
        if (lastLatLng) {
          Leaflet.circleMarker(lastLatLng, {
            radius: 6,
            color: "#ffffff",
            weight: 2,
            fillColor: activity.color,
            fillOpacity: 1,
          }).addTo(group);
        }

        if (visibleCollections.has(ci)) {
          bounds.extend(poly.getBounds());
        }
      }
    }
  }

  // hide collections that are toggled off
  leafletState.collectionGroups.forEach((group, ci) => {
    if (!visibleCollections.has(ci)) {
      group.remove();
    }
  });

  if (allVisible.length > 0 && allVisible.every((e) => e.routeData.points.length === 1)) {
    const firstPoint = allVisible[0].routeData.points[0];
    leafletState.map.setView([firstPoint.lat, firstPoint.lon], 11);
  } else if (bounds.isValid()) {
    // Zoom out a bit more by default (maxZoom 11 instead of 13) and center on bounds
    leafletState.map.fitBounds(bounds, { padding: [72, 72], maxZoom: 11 });

    // If we have live data, ensure we are focused on the latest position
    const latestEntries = allVisible.filter(e => e.routeData.points.length > 0);
    if (latestEntries.length > 0) {
      // Find the most recently updated activity
      const newest = latestEntries.sort((a, b) => {
        const tA = a.routeData.summary.lastReportedTime ? new Date(a.routeData.summary.lastReportedTime).getTime() : 0;
        const tB = b.routeData.summary.lastReportedTime ? new Date(b.routeData.summary.lastReportedTime).getTime() : 0;
        return tB - tA;
      })[0];
      
      const lastPoint = newest.routeData.points.at(-1);
      if (lastPoint) {
        leafletState.map.panTo([lastPoint.lat, lastPoint.lon]);
      }
    }
  }

  mapShell.classList.remove("hidden");
  placeholder.classList.add("hidden");

  updateMapStats(allVisible);
  renderLiveStats(allVisible);
  renderGraphs(allVisible);

  requestAnimationFrame(() => {
    leafletState?.map.invalidateSize();
  });
}

function getVisibleRouteEntries(): RouteEntry[] {
  return allRouteEntries.filter((e) => visibleCollections.has(e.collectionIndex));
}

function selectCollection(collectionIndex: number): void {
  if (!leafletState || !trackerCollections[collectionIndex]) {
    return;
  }

  activeCollectionIndex = collectionIndex;
  visibleCollections = new Set([collectionIndex]);

  leafletState.collectionGroups.forEach((group, ci) => {
    if (ci === collectionIndex) {
      group.addTo(leafletState.map);
    } else {
      group.remove();
    }
  });

  const visible = getVisibleRouteEntries();
  updateMapStats(visible);
  renderLiveStats(visible);
  renderGraphs(visible);
  renderActivityList(trackerCollections, activeCollectionIndex);
  updateCollectionButtonStates();
}

function updateCollectionButtonStates(): void {
  const controls = getElement<HTMLDivElement>("collection-controls");
  if (!controls) {
    return;
  }

  controls.querySelectorAll<HTMLButtonElement>("[data-collection-index]").forEach((btn) => {
    const ci = Number(btn.dataset.collectionIndex);
    const selected = activeCollectionIndex === ci;
    btn.classList.toggle("collection-btn--off", !selected);
    btn.setAttribute("aria-selected", selected ? "true" : "false");
  });
}

function renderCollectionControls(collections: TrackerCollection[]): void {
  const controls = getElement<HTMLDivElement>("collection-controls");
  if (!controls) {
    return;
  }

  if (collections.length < 2) {
    controls.classList.add("hidden");
    return;
  }

  controls.classList.remove("hidden");
  controls.innerHTML = collections
    .map((col, ci) => {
      const selected = activeCollectionIndex === ci;
      return `<button
        class="collection-btn"
        role="tab"
        aria-selected="${selected ? "true" : "false"}"
        data-collection-index="${ci}"
        style="--col-color:${escapeHtml(col.color)}"
        type="button"
      >${escapeHtml(col.name)}</button>`;
    })
    .join("");

  controls.querySelectorAll<HTMLButtonElement>("[data-collection-index]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ci = Number(btn.dataset.collectionIndex);
      selectCollection(ci);
    });
  });
}

function updateMapStats(routes: RouteEntry[]): void {
  const totalDistanceMeters = routes.reduce(
    (sum, e) => sum + (e.routeData.summary.totalDistanceMeters ?? 0),
    0,
  );
  const totalDurationSecs = routes.reduce(
    (sum, e) => sum + (e.routeData.summary.totalDurationSecs ?? 0),
    0,
  );
  const pointCount = routes.reduce((sum, e) => sum + e.routeData.summary.pointCount, 0);
  const lastUpdated = routes
    .map((e) => e.routeData.summary.lastReportedTime)
    .filter((v): v is string => Boolean(v))
    .sort()
    .at(-1);

  setText("stat-distance", formatDistance(totalDistanceMeters));
  setText("stat-duration", formatDuration(totalDurationSecs));
  setText("stat-updated", formatDateTime(lastUpdated));
  setText("stat-points", String(pointCount));

  const stats = getElement<HTMLDivElement>("map-stats");
  if (stats) {
    stats.classList.remove("hidden");
  }
}

function hideMapStats(): void {
  const stats = getElement<HTMLDivElement>("map-stats");
  if (stats) {
    stats.classList.add("hidden");
  }
}

function renderLiveStats(routes: RouteEntry[]): void {
  const container = getElement<HTMLDivElement>("live-stats");
  if (!container) {
    return;
  }

  const cards = routes
    .filter((entry) => entry.routeData.summary.isActive)
    .map((entry) => {
      const latestPoint = entry.routeData.points.at(-1);
      if (!latestPoint) {
        return "";
      }

      const speedKmh =
        typeof latestPoint.speedMetersPerSec === "number"
          ? latestPoint.speedMetersPerSec * 3.6
          : deriveSpeedKmh(latestPoint, entry.routeData.points.at(-2));

      return `
        <article class="live-stat-card">
          <h3>${escapeHtml(entry.activityLabel)}</h3>
          <div class="live-stat-grid">
            <span>Speed <strong>${escapeHtml(formatSpeed(speedKmh))}</strong></span>
            <span>Distance <strong>${escapeHtml(formatDistance(latestPoint.distanceMeters))}</strong></span>
            <span>Elevation <strong>${escapeHtml(formatElevation(latestPoint.elevation))}</strong></span>
            <span>HR <strong>${escapeHtml(formatHeartRate(latestPoint.heartRateBeatsPerMin))}</strong></span>
            <span>Cadence <strong>${escapeHtml(formatCadence(latestPoint.cadenceCyclesPerMin))}</strong></span>
            <span>Power <strong>${escapeHtml(formatPower(latestPoint.powerWatts))}</strong></span>
            <span>Duration <strong>${escapeHtml(formatDuration(latestPoint.durationSecs))}</strong></span>
            <span>Updated <strong>${escapeHtml(formatDateTime(entry.routeData.summary.lastReportedTime))}</strong></span>
          </div>
        </article>`;
    })
    .filter(Boolean)
    .join("");

  if (!cards) {
    hideLiveStats();
    return;
  }

  container.innerHTML = cards;
  container.classList.remove("hidden");
}

function hideLiveStats(): void {
  const container = getElement<HTMLDivElement>("live-stats");
  if (container) {
    container.classList.add("hidden");
    container.innerHTML = "";
  }
}

function renderGraphs(routes: RouteEntry[]): void {
  const graphSection = getElement<HTMLElement>("route-graphs");
  const graphHeading = getElement<HTMLElement>("graphs-heading");
  const switcher = getElement<HTMLDivElement>("graph-switcher");
  const canvas = getElement<HTMLDivElement>("graph-canvas");

  if (!graphSection || !graphHeading || !switcher || !canvas) {
    return;
  }

  if (routes.length === 0) {
    hideGraphs();
    return;
  }

  const metrics = getGraphMetrics();
  const available = metrics
    .map((metric) => ({
      metric,
      series: buildCombinedSeries(routes, metric.selectPoint),
    }))
    .filter((entry) => entry.series.length > 0);

  if (available.length === 0) {
    hideGraphs();
    return;
  }

  if (!available.some((entry) => entry.metric.key === activeGraphMetric)) {
    activeGraphMetric = available[0].metric.key;
  }

  switcher.innerHTML = available
    .map(
      ({ metric }) => `
      <button class="graph-toggle-button ${metric.key === activeGraphMetric ? "is-active" : ""}" type="button" data-metric="${metric.key}" role="tab" aria-selected="${metric.key === activeGraphMetric ? "true" : "false"}">
        ${escapeHtml(metric.title)}
      </button>`,
    )
    .join("");

  const selected = available.find((entry) => entry.metric.key === activeGraphMetric) ?? available[0];
  graphHeading.textContent = selected.metric.title;
  canvas.innerHTML = `
    <article class="graph-card graph-card--full">
      <div class="graph-card-header">
        <h3>${escapeHtml(selected.metric.title)}</h3>
        <span class="graph-axis-label">${escapeHtml(selected.metric.xLabel)} → ${escapeHtml(selected.metric.yLabel)}</span>
      </div>
      <div class="graph-canvas">${buildLineChartSvg({
        series: selected.series,
        xFormatter: selected.metric.xFormatter,
        yFormatter: selected.metric.yFormatter,
        baselineAtZero: selected.metric.baselineAtZero,
        xLabel: selected.metric.xLabel,
        yLabel: selected.metric.yLabel,
      })}</div>
    </article>`;

  switcher.querySelectorAll<HTMLButtonElement>("[data-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      const metric = button.dataset.metric as GraphMetricConfig["key"] | undefined;
      if (!metric || metric === activeGraphMetric) {
        return;
      }
      activeGraphMetric = metric;
      renderGraphs(routes);
    });
  });

  graphSection.classList.remove("hidden");
}

function hideGraphs(): void {
  const graphSection = getElement<HTMLElement>("route-graphs");
  const switcher = getElement<HTMLDivElement>("graph-switcher");
  const canvas = getElement<HTMLDivElement>("graph-canvas");

  if (graphSection) {
    graphSection.classList.add("hidden");
  }
  if (switcher) {
    switcher.innerHTML = "";
  }
  if (canvas) {
    canvas.innerHTML = "";
  }
}

function getGraphMetrics(): GraphMetricConfig[] {
  return [
    {
      key: "speed",
      title: "Speed",
      xLabel: "Distance",
      yLabel: "km/h",
      baselineAtZero: true,
      xFormatter: formatDistance,
      yFormatter: (v) => `${Math.round(v)} km/h`,
      selectPoint: (point, prev) => {
        if (typeof point.distanceMeters !== "number") {
          return null;
        }
        if (typeof point.speedMetersPerSec === "number") {
          return { x: point.distanceMeters, y: point.speedMetersPerSec * 3.6 };
        }
        const derived = deriveSpeedKmh(point, prev);
        return typeof derived === "number" ? { x: point.distanceMeters, y: derived } : null;
      },
    },
    {
      key: "elevation",
      title: "Elevation",
      xLabel: "Distance",
      yLabel: "Metres",
      baselineAtZero: false,
      xFormatter: formatDistance,
      yFormatter: (v) => `${Math.round(v)} m`,
      selectPoint: (point) =>
        typeof point.distanceMeters === "number" && typeof point.elevation === "number" && point.elevation !== 0
          ? { x: point.distanceMeters, y: point.elevation }
          : null,
    },
    {
      key: "heartRate",
      title: "Heart rate",
      xLabel: "Distance",
      yLabel: "bpm",
      baselineAtZero: true,
      xFormatter: formatDistance,
      yFormatter: (v) => `${Math.round(v)} bpm`,
      selectPoint: (point) =>
        typeof point.distanceMeters === "number" && typeof point.heartRateBeatsPerMin === "number"
          ? { x: point.distanceMeters, y: point.heartRateBeatsPerMin }
          : null,
    },
    {
      key: "power",
      title: "Power",
      xLabel: "Distance",
      yLabel: "watts",
      baselineAtZero: true,
      xFormatter: formatDistance,
      yFormatter: (v) => `${Math.round(v)} w`,
      selectPoint: (point) =>
        typeof point.distanceMeters === "number" && typeof point.powerWatts === "number"
          ? { x: point.distanceMeters, y: point.powerWatts }
          : null,
    },
    {
      key: "cadence",
      title: "Cadence",
      xLabel: "Distance",
      yLabel: "rpm",
      baselineAtZero: true,
      xFormatter: formatDistance,
      yFormatter: (v) => `${Math.round(v)} rpm`,
      selectPoint: (point) =>
        typeof point.distanceMeters === "number" && typeof point.cadenceCyclesPerMin === "number"
          ? { x: point.distanceMeters, y: point.cadenceCyclesPerMin }
          : null,
    },
  ];
}

/**
 * Build one ChartSeries per activity with a continuous x-axis across all activities.
 * Each activity's x values are offset by the cumulative maximum x of all prior activities.
 */
function buildCombinedSeries(
  routes: RouteEntry[],
  selectPoint: (point: GarminTrackPoint, prev?: GarminTrackPoint) => ChartSeriesPoint | null,
): ChartSeries[] {
  const result: ChartSeries[] = [];
  let xOffset = 0;

  for (const entry of routes) {
    const rawPoints = entry.routeData.points
      .map((point, index, all) => selectPoint(point, index > 0 ? all[index - 1] : undefined))
      .filter((p): p is ChartSeriesPoint => p !== null && Number.isFinite(p.x) && Number.isFinite(p.y));

    if (rawPoints.length < 2) {
      continue;
    }

    const xMax = rawPoints.at(-1)!.x;
    const offsetPoints = rawPoints.map((p) => ({ x: p.x + xOffset, displayX: p.x, y: p.y }));

    result.push({
      color: entry.color,
      label: entry.activityLabel,
      xTotal: xMax,
      points: offsetPoints,
    });

    xOffset += xMax;
  }

  return result;
}

function deriveSpeedKmh(point: GarminTrackPoint, prev?: GarminTrackPoint): number | null {
  if (
    !prev ||
    typeof prev.distanceMeters !== "number" ||
    typeof point.distanceMeters !== "number" ||
    typeof prev.durationSecs !== "number" ||
    typeof point.durationSecs !== "number"
  ) {
    return null;
  }

  const dDist = point.distanceMeters - prev.distanceMeters;
  const dTime = point.durationSecs - prev.durationSecs;

  if (dDist <= 0 || dTime <= 0) {
    return null;
  }

  return (dDist / dTime) * 3.6;
}

function buildLineChartSvg(options: {
  series: ChartSeries[];
  xFormatter: (value: number) => string;
  yFormatter: (value: number) => string;
  baselineAtZero: boolean;
  xLabel: string;
  yLabel: string;
}): string {
  const { series, xFormatter, yFormatter, baselineAtZero, xLabel, yLabel } = options;
  const width = 680;
  const height = 240;
  const padding = { top: 16, right: 16, bottom: 34, left: 48 };

  const allX = series.flatMap((s) => s.points.map((p) => p.x));
  const allY = series.flatMap((s) => s.points.map((p) => p.y));
  const xMin = 0;
  const xMax = Math.max(...allX, 1);
  const rawYMin = Math.min(...allY);
  const rawYMax = Math.max(...allY);
  const equalPad = rawYMax === rawYMin ? Math.max(Math.abs(rawYMax) * 0.05, 1) : 0;
  const yMin = baselineAtZero ? 0 : rawYMin - equalPad;
  const yMax = rawYMax + equalPad;
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const yRange = Math.max(yMax - yMin, 1);

  const scaleX = (v: number) => padding.left + (v / xMax) * chartWidth;
  const scaleY = (v: number) => padding.top + chartHeight - ((v - yMin) / yRange) * chartHeight;

  const gridLinesCount = 6;
  const gridLines = Array.from({ length: gridLinesCount }, (_, i) => {
    const v = yMin + (yRange / (gridLinesCount - 1)) * i;
    const y = scaleY(v);
    return `
      <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" class="graph-grid-line" />
      <text x="${padding.left - 4}" y="${y}" text-anchor="end" dominant-baseline="middle" class="graph-label">${escapeHtml(yFormatter(v))}</text>
    `;
  }).join("");

  const xTicksCount = 10;
  const xTicks = Array.from({ length: xTicksCount }, (_, i) => {
    const v = xMin + ((xMax - xMin) / (xTicksCount - 1)) * i;
    const x = scaleX(v);
    return `<text x="${x}" y="${height - padding.bottom + 18}" text-anchor="${i === 0 ? "start" : i === xTicksCount - 1 ? "end" : "middle"}" class="graph-label">${escapeHtml(xFormatter(v))}</text>`;
  }).join("");

  const paths = series
    .map((s) => {
      const d = s.points
        .map((p, i) => `${i === 0 ? "M" : "L"} ${scaleX(p.x).toFixed(2)} ${scaleY(p.y).toFixed(2)}`)
        .join(" ");
      return `<path d="${d}" fill="none" stroke="${escapeHtml(s.color)}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />`;
    })
    .join("");

  const hoverPoints = series
    .map((s) =>
      s.points
        .map((p) => {
          const tooltip = `${s.label}
Current ${xLabel}: ${xFormatter(p.displayX ?? p.x)}
Current ${yLabel}: ${yFormatter(p.y)}
Total ${xLabel}: ${xFormatter(s.xTotal)}`;
          return `<circle cx="${scaleX(p.x).toFixed(2)}" cy="${scaleY(p.y).toFixed(2)}" r="5" fill="${escapeHtml(s.color)}" fill-opacity="0.001"><title>${escapeXml(tooltip)}</title></circle>`;
        })
        .join(""),
    )
    .join("");

  const uniqueLabels = [...new Map(series.map((s) => [s.label, s])).values()];
  const legend = uniqueLabels
    .map(
      (s, i) => `
      <g transform="translate(${padding.left + i * 170}, ${height - 6})">
        <line x1="0" y1="-4" x2="16" y2="-4" stroke="${escapeHtml(s.color)}" stroke-width="3" />
        <text x="22" y="0" class="graph-legend-text">${escapeHtml(s.label)}</text>
      </g>`,
    )
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" class="graph-svg" role="img">
      <g>
        ${gridLines}
        <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" class="graph-axis" />
        <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" class="graph-axis" />
        ${paths}
        ${hoverPoints}
        <text x="${padding.left}" y="${padding.top - 2}" class="graph-label">${escapeHtml(yFormatter(yMax))}</text>
        <text x="${padding.left}" y="${height - padding.bottom + 26}" class="graph-label">${escapeHtml(xFormatter(xMin))}</text>
        <text x="${width - padding.right}" y="${height - padding.bottom + 26}" text-anchor="end" class="graph-label">${escapeHtml(xFormatter(xMax))}</text>
        <text x="${padding.left}" y="${height - padding.bottom + 26}" dy="-16" class="graph-label">${escapeHtml(yFormatter(yMin))}</text>
        ${legend}
      </g>
    </svg>`;
}

function renderActivityList(collections: TrackerCollection[], selectedCollectionIndex: number | null): void {
  const activityList = getElement<HTMLDivElement>("activity-list");
  if (!activityList) {
    return;
  }

  const cards = collections
    .flatMap((col, ci) =>
      (selectedCollectionIndex === null || selectedCollectionIndex === ci ? col.activities : []).map(
        (activity, ai) => {
          const entry = allRouteEntries.find((e) => e.collectionIndex === ci && e.activityIndex === ai);
          const gpxHref = entry ? buildGpxDownloadUrl(entry.routeData.points, `${col.name} #${ai + 1}`) : null;
          const statusText = getActivityStatusLabel(activity.routeData, activity.garminLivetrackUrl, activity.stravaActivityId);
          const metrics = entry ? renderActivityMetrics(entry.routeData) : "";
          const notes = activity.notes ? `<p class="activity-notes">${escapeHtml(activity.notes)}</p>` : "";
          const garminLink = activity.garminLivetrackUrl
            ? `<a class="button-link" href="${escapeHtml(activity.garminLivetrackUrl)}" target="_blank" rel="noreferrer">Open in Garmin</a>`
            : "";
          const stravaLink = activity.stravaActivityId
            ? `<a class="button-link" href="https://www.strava.com/activities/${encodeURIComponent(activity.stravaActivityId)}" target="_blank" rel="noreferrer">Open in Strava</a>`
            : "";
          const gpxLink = gpxHref
            ? `<a class="button-link button-link-secondary" href="${gpxHref}" download="${slugify(col.name)}-${ai + 1}.gpx">Download GPX</a>`
            : "";

          return `
          <article class="activity-card">
            <div class="activity-card__header">
              <span class="activity-swatch" style="background:${escapeHtml(activity.color)}"></span>
              <div>
                <p class="activity-collection">${escapeHtml(col.name)}</p>
                <p class="activity-status">${escapeHtml(statusText)}</p>
              </div>
            </div>
            ${notes}
            ${metrics}
            <div class="activity-actions">${gpxLink}${garminLink}${stravaLink}</div>
          </article>`;
        },
      ),
    )
    .join("");

  if (!cards) {
    activityList.classList.add("hidden");
    return;
  }

  activityList.innerHTML = cards;
  activityList.classList.remove("hidden");
}

function renderActivityMetrics(routeData: GarminRouteOk): string {
  return `
    <div class="activity-metrics">
      <span>${escapeHtml(formatDistance(routeData.summary.totalDistanceMeters))}</span>
      <span>${escapeHtml(formatDuration(routeData.summary.totalDurationSecs))}</span>
      <span>${escapeHtml(String(routeData.summary.pointCount))} pts</span>
      ${routeData.summary.isActive ? '<span class="activity-live-pill">Live</span>' : ""}
    </div>`;
}

function getActivityStatusLabel(
  routeData: GarminRouteData | null,
  livetrackUrl: string | null,
  stravaActivityId: string | null,
): string {
  if (!livetrackUrl && !stravaActivityId) {
    return "No Garmin LiveTrack URL or Strava activity ID yet.";
  }

  if (!routeData) {
    return "Waiting for the next site refresh.";
  }

  if (routeData.status === "ok") {
    return routeData.summary.isActive
      ? `Live now · ${formatDistance(routeData.summary.totalDistanceMeters)} · ${formatDuration(routeData.summary.totalDurationSecs)}`
      : `${formatDistance(routeData.summary.totalDistanceMeters)} · ${formatDuration(routeData.summary.totalDurationSecs)}`;
  }

  if (routeData.status === "empty") {
    return livetrackUrl
      ? "Session exists but no route points are available yet."
      : "Strava activity exists but no route points are available yet.";
  }

  return livetrackUrl
    ? "Route extraction failed; Garmin fallback is still available."
    : "Route extraction failed; Strava fallback is still available.";
}

function buildPlaceholderCopy(collections: TrackerCollection[]): string {
  const anyUrl = collections.some((col) =>
    col.activities.some((a) => a.garminLivetrackUrl || a.stravaActivityId),
  );

  if (!anyUrl) {
    return "Add Garmin LiveTrack URLs or Strava activity IDs in <code>live-tracking.yaml</code> once the ride has started.";
  }

  return "The last build could not extract route data. Use the source links in the activity list as a fallback.";
}

function buildGpxDownloadUrl(points: GarminTrackPoint[], title: string): string {
  const gpx = buildGpxDocument(points, title);
  const url = URL.createObjectURL(new Blob([gpx], { type: "application/gpx+xml" }));
  gpxDownloadUrls.push(url);
  return url;
}

function revokeGpxUrls(): void {
  gpxDownloadUrls.forEach((url) => URL.revokeObjectURL(url));
  gpxDownloadUrls = [];
}

function buildGpxDocument(points: GarminTrackPoint[], title: string): string {
  const trkpts = points
    .map((p) => {
      const ele = typeof p.elevation === "number" ? `<ele>${p.elevation.toFixed(2)}</ele>` : "";
      const time = p.time ? `<time>${escapeXml(p.time)}</time>` : "";
      return `<trkpt lat="${p.lat}" lon="${p.lon}">${ele}${time}</trkpt>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="follow-my-garmin" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>${escapeXml(title)}</name>
    <trkseg>${trkpts}</trkseg>
  </trk>
</gpx>`;
}

function formatDistance(distanceMeters?: number): string {
  if (typeof distanceMeters !== "number" || Number.isNaN(distanceMeters)) {
    return "-";
  }
  return distanceMeters >= 1000 ? `${(distanceMeters / 1000).toFixed(1)} km` : `${Math.round(distanceMeters)} m`;
}

function formatSpeed(speedKmh?: number | null): string {
  if (typeof speedKmh !== "number" || Number.isNaN(speedKmh)) {
    return "-";
  }
  return `${speedKmh.toFixed(1)} km/h`;
}

function formatElevation(elevationMeters?: number): string {
  if (typeof elevationMeters !== "number" || Number.isNaN(elevationMeters)) {
    return "-";
  }
  return `${Math.round(elevationMeters)} m`;
}

function formatHeartRate(heartRateBpm?: number): string {
  if (typeof heartRateBpm !== "number" || Number.isNaN(heartRateBpm)) {
    return "-";
  }
  return `${Math.round(heartRateBpm)} bpm`;
}

function formatCadence(cadenceRpm?: number): string {
  if (typeof cadenceRpm !== "number" || Number.isNaN(cadenceRpm)) {
    return "-";
  }
  return `${Math.round(cadenceRpm)} rpm`;
}

function formatPower(powerWatts?: number): string {
  if (typeof powerWatts !== "number" || Number.isNaN(powerWatts)) {
    return "-";
  }
  return `${Math.round(powerWatts)} w`;
}

function formatDuration(durationSecs?: number): string {
  if (typeof durationSecs !== "number" || Number.isNaN(durationSecs)) {
    return "-";
  }
  const hours = Math.floor(durationSecs / 3600);
  const minutes = Math.floor((durationSecs % 3600) / 60);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function formatDateTime(isoDateTime?: string): string {
  if (!isoDateTime) {
    return "-";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoDateTime));
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function setText(id: string, value: string): void {
  const el = getElement<HTMLElement>(id);
  if (el) {
    el.textContent = value;
  }
}

function getElement<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}
