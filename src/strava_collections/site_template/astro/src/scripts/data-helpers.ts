import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { GarminRouteData, GarminTrackPoint } from "../data/trip";

export interface GarminHydratedQuery {
  queryKey?: unknown[];
  state?: {
    data?: unknown;
  };
}

export interface GarminSessionData {
  start?: string;
  end?: string;
  postTrackPointFrequency?: number;
  position?: {
    lat?: number;
    lon?: number;
  };
}

export interface GarminTrackPointSource {
  dateTime?: string;
  reportedTime?: string;
  altitude?: number;
  speed?: number;
  speedMetersPerSec?: number;
  heartRateBeatsPerMin?: number;
  cadenceCyclesPerMin?: number;
  powerWatts?: number;
  totalDurationSecs?: number;
  durationSecs?: number;
  totalDistanceMeters?: number;
  distanceMeters?: number;
  position?: {
    lat?: number;
    lon?: number;
  };
}

const hydrationPattern = /self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)/gs;

export function parseGpxPoints(
  gpxContent: string,
  options: { includeTelemetry?: boolean } = {},
): GarminTrackPoint[] {
  const includeTelemetry = options.includeTelemetry ?? true;
  const points: GarminTrackPoint[] = [];
  const trkptRegex =
    /<trkpt lat="([-0-9.]+)" lon="([-0-9.]+)">([\s\S]*?)<\/trkpt>/g;
  let match;
  while ((match = trkptRegex.exec(gpxContent)) !== null) {
    const lat = parseFloat(match[1]);
    const lon = parseFloat(match[2]);
    const inner = match[3];

    const point: GarminTrackPoint = { lat, lon };

    if (!includeTelemetry) {
      points.push(point);
      continue;
    }

    const eleMatch = /<ele>([-0-9.]+)<\/ele>/.exec(inner);
    if (eleMatch) point.elevation = parseFloat(eleMatch[1]);

    const timeMatch = /<time>(.*?)<\/time>/.exec(inner);
    if (timeMatch) point.time = timeMatch[1];

    const hrMatch = /<gpxtpx:hr>(\d+)<\/gpxtpx:hr>/.exec(inner);
    if (hrMatch) point.heartRateBeatsPerMin = parseInt(hrMatch[1], 10);

    const cadMatch = /<gpxtpx:cad>(\d+)<\/gpxtpx:cad>/.exec(inner);
    if (cadMatch) point.cadenceCyclesPerMin = parseInt(cadMatch[1], 10);

    const powerMatch = /<power>(\d+)<\/power>/.exec(inner);
    if (powerMatch) point.powerWatts = parseInt(powerMatch[1], 10);

    points.push(point);
  }

  if (includeTelemetry) {
    let totalDistance = 0;
    let totalDuration = 0;
    for (let i = 0; i < points.length; i++) {
      if (i > 0) {
        const p1 = points[i - 1];
        const p2 = points[i];
        const d = calculateDistance(p1.lat, p1.lon, p2.lat, p2.lon);
        totalDistance += d;
        if (p1.time && p2.time) {
          const dt =
            (new Date(p2.time).getTime() - new Date(p1.time).getTime()) / 1000;
          if (dt > 0) totalDuration += dt;
        }
      }
      points[i].distanceMeters = totalDistance;
      points[i].durationSecs = totalDuration;
    }
  }

  return points;
}

function calculateDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function downsamplePoints<T>(points: T[], maxPoints = 1000): T[] {
  if (points.length <= maxPoints) return points;
  if (maxPoints <= 2) return [points[0], points[points.length - 1]];

  const sampled: T[] = [];
  const lastIndex = points.length - 1;
  const step = lastIndex / (maxPoints - 1);

  for (let i = 0; i < maxPoints; i++) {
    sampled.push(points[Math.round(i * step)]);
  }

  return sampled;
}

export function loadPlannedRouteData(
  input: string | string[] | undefined | null,
): { points: Array<{ lat: number; lon: number }> } | null {
  if (!input) return null;
  const filenames = Array.isArray(input) ? input : [input];
  const allPoints: Array<{ lat: number; lon: number }> = [];

  for (const filename of filenames) {
    if (!filename) continue;

    const possiblePaths = [
      filename, // Try as absolute path
      join(process.cwd(), filename),
      join(process.cwd(), "../source", filename),
      join(process.cwd(), "../..", filename), // Project root from docs/astro
      join(process.cwd(), "../../..", filename), // Project root from docs/astro/src/pages
    ];

    let found = false;
    for (const p of possiblePaths) {
      if (existsSync(p)) {
        try {
          const content = readFileSync(p, "utf-8");
          const points = downsamplePoints(
            parseGpxPoints(content, { includeTelemetry: false }),
          );
          if (points.length > 0) {
            allPoints.push(...points);
            found = true;
            break;
          }
        } catch (error) {
          console.warn(`Failed to load GPX file ${p}:`, error);
        }
      }
    }

    if (!found) {
      console.warn(`Could not find GPX file: ${filename}`);
    }
  }

  return allPoints.length > 0 ? { points: allPoints } : null;
}

export function loadPlannedRoutesIndividually(
  input: string | string[] | undefined | null,
): Array<{ points: Array<{ lat: number; lon: number }> }> {
  if (!input) return [];
  const filenames = Array.isArray(input) ? input : [input];
  const routes: Array<{ points: Array<{ lat: number; lon: number }> }> = [];

  for (const filename of filenames) {
    if (!filename) continue;

    const possiblePaths = [
      filename, // Try as absolute path
      join(process.cwd(), filename),
      join(process.cwd(), "../source", filename),
      join(process.cwd(), "../..", filename), // Project root from docs/astro
      join(process.cwd(), "../../..", filename), // Project root from docs/astro/src/pages
    ];

    let found = false;
    for (const p of possiblePaths) {
      if (existsSync(p)) {
        try {
          const content = readFileSync(p, "utf-8");
          const points = downsamplePoints(
            parseGpxPoints(content, { includeTelemetry: false }),
          );
          if (points.length > 0) {
            routes.push({ points });
            found = true;
            break;
          }
        } catch (error) {
          console.warn(`Failed to load GPX file ${p}:`, error);
        }
      }
    }

    if (!found) {
      console.warn(`Could not find GPX file: ${filename}`);
    }
  }

  return routes;
}

export function loadStravaRouteData(activities: any[]): GarminRouteData[] {
  if (activities.length === 0) return [];

  const results: (GarminRouteData | null)[] = activities.map(() => null);

  // First, try to load from local GPX files if they exist
  activities.forEach((a, i) => {
    const activityId =
      a.stravaActivityId || (a.strava_id ? String(a.strava_id[0]) : "");
    if (!activityId) return;

    const filename = `activity-${activityId}.gpx`;
    const possiblePaths = [
      join(process.cwd(), "../source/_static", filename),
      join(process.cwd(), "public/_static", filename),
      join(process.cwd(), filename),
    ];

    for (const p of possiblePaths) {
      if (existsSync(p)) {
        const content = readFileSync(p, "utf-8");
        const points = parseGpxPoints(content, { includeTelemetry: true });
        if (points.length > 0) {
          const downsampled = downsamplePoints(points, 500);
          results[i] = {
            status: "ok",
            points: downsampled,
            summary: {
              pointCount: downsampled.length,
              isActive: false,
            },
          };
          break;
        }
      }
    }
  });

  // If all activities were loaded from files, return early
  if (results.every((r) => r !== null)) {
    return results as GarminRouteData[];
  }

  // Otherwise, fallback to calling Python for the remaining ones
  const missingActivityIds = activities
    .map((a, i) => (results[i] === null ? a : null))
    .filter((a) => a !== null)
    .map(
      (a) => a.stravaActivityId || (a.strava_id ? String(a.strava_id[0]) : ""),
    )
    .filter((id) => id.length > 0);

  if (missingActivityIds.length === 0) {
    return results.map((r) => r ?? ({ status: "error" } as GarminRouteData));
  }

  const repoSrc = join(process.cwd(), "..", "..", "src");
  const env = { ...process.env };
  if (existsSync(repoSrc)) {
    env.PYTHONPATH = env.PYTHONPATH ? `${repoSrc}:${env.PYTHONPATH}` : repoSrc;
  }

  const output = execFileSync(
    "python3",
    ["-m", "strava_collections.live_tracking_export", ...missingActivityIds],
    {
      cwd: process.cwd(),
      encoding: "utf-8",
      env,
      maxBuffer: 10 * 1024 * 1024,
    },
  );
  const exported = JSON.parse(output) as Record<
    string,
    string | GarminRouteData
  >;

  return activities.map((a, i) => {
    if (results[i] !== null) return results[i] as GarminRouteData;

    const id =
      a.stravaActivityId || (a.strava_id ? String(a.strava_id[0]) : "");
    const rawData = exported[id];
    if (typeof rawData === "string") {
      const points = parseGpxPoints(rawData, { includeTelemetry: true });
      const downsampled = downsamplePoints(points, 500);
      if (downsampled.length > 0) {
        return {
          status: "ok",
          points: downsampled,
          summary: {
            pointCount: downsampled.length,
            isActive: false,
          },
        };
      }
      return { status: "empty" };
    }
    return rawData ?? { status: "error" };
  });
}

export const parseLivetrackUrl = (url: string): boolean =>
  /\/session\/([a-z0-9-]+)\/token\/([a-z0-9]+)/i.test(url);

export async function loadGarminRouteData(
  activities: any[],
  collectionMetadata?: any,
): Promise<(GarminRouteData | null)[]> {
  return Promise.all(
    activities.map(async (activity) => {
      const url =
        activity.garminLivetrackUrl ||
        (activity === activities[activities.length - 1]
          ? collectionMetadata?.garminLivetrackUrl
          : null);
      if (!url || !parseLivetrackUrl(url)) {
        return null;
      }

      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const response = await fetch(url, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!response.ok) {
          return { status: "error" } as const;
        }

        const html = await response.text();
        const parsed = parseTrackDataFromHtml(html);
        if ("errorDetail" in parsed) {
          return { status: "error" } as const;
        }

        const points = parsed.points
          .map((point) => normalizeTrackPoint(point))
          .filter((point): point is GarminTrackPoint => point !== null);

        if (points.length === 0) {
          return { status: "empty" } as const;
        }

        return {
          status: "ok",
          points,
          summary: buildRouteSummary(points, parsed.session),
        } as const;
      } catch {
        return { status: "error" } as const;
      }
    }),
  );
}

export function parseTrackDataFromHtml(
  html: string,
):
  | { points: GarminTrackPointSource[]; session: GarminSessionData }
  | { errorDetail: string } {
  let trackQuery: GarminHydratedQuery | undefined;
  let sessionQuery: GarminHydratedQuery | undefined;

  for (const match of html.matchAll(hydrationPattern)) {
    try {
      const decoded = JSON.parse(`"${match[1]}"`) as string;

      for (const line of decoded.split("\n")) {
        const payloadSeparator = line.indexOf(":");
        if (payloadSeparator === -1) {
          continue;
        }

        const payloadRaw = line.slice(payloadSeparator + 1);
        if (!payloadRaw.startsWith("{") && !payloadRaw.startsWith("[")) {
          continue;
        }

        const payload = JSON.parse(payloadRaw) as unknown;
        const queries = collectQueries(payload);

        if (!trackQuery) {
          trackQuery = queries.find(
            (query) => query.queryKey?.at(-1) === "track-points",
          );
        }
        if (!sessionQuery) {
          sessionQuery = queries.find(
            (query) =>
              Array.isArray(query.queryKey) &&
              query.queryKey[0] === "session" &&
              query.queryKey.length === 3,
          );
        }
      }
    } catch {
      continue;
    }
  }

  if (sessionQuery) {
    const session = asSessionData(sessionQuery.state?.data);
    const trackPages = trackQuery ? asTrackPages(trackQuery.state?.data) : [];
    const points = trackPages.flatMap((page) => page.trackPoints ?? []);

    if (points.length === 0 && session.position?.lat && session.position?.lon) {
      points.push({
        position: session.position,
        dateTime: session.end || session.start,
        reportedTime: session.end || session.start,
      });
    }

    return { points, session };
  }

  return { errorDetail: "Could not find Garmin hydration session data." };
}

function collectQueries(value: unknown): GarminHydratedQuery[] {
  const out: GarminHydratedQuery[] = [];
  const visit = (node: unknown): void => {
    if (!node) return;
    if (Array.isArray(node)) {
      node.forEach(visit);
      return;
    }
    if (typeof node !== "object") return;
    const maybeQuery = node as GarminHydratedQuery;
    if (Array.isArray(maybeQuery.queryKey)) out.push(maybeQuery);
    Object.values(node as Record<string, unknown>).forEach(visit);
  };
  visit(value);
  return out;
}

function asTrackPages(
  value: unknown,
): Array<{ trackPoints?: GarminTrackPointSource[] }> {
  if (!value || typeof value !== "object" || !("pages" in value)) return [];
  const pages = (value as { pages?: unknown[] }).pages;
  return Array.isArray(pages)
    ? (pages as Array<{ trackPoints?: GarminTrackPointSource[] }>)
    : [];
}

function asSessionData(value: unknown): GarminSessionData {
  if (!value || typeof value !== "object") return {};
  return value as GarminSessionData;
}

function normalizeTrackPoint(
  point: GarminTrackPointSource,
): GarminTrackPoint | null {
  const lat = point.position?.lat;
  const lon = point.position?.lon;
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  return {
    lat,
    lon,
    elevation: typeof point.altitude === "number" ? point.altitude : undefined,
    speedMetersPerSec:
      typeof point.speedMetersPerSec === "number"
        ? point.speedMetersPerSec
        : typeof point.speed === "number"
          ? point.speed
          : undefined,
    heartRateBeatsPerMin:
      typeof point.heartRateBeatsPerMin === "number" &&
      point.heartRateBeatsPerMin > 0
        ? point.heartRateBeatsPerMin
        : undefined,
    cadenceCyclesPerMin:
      typeof point.cadenceCyclesPerMin === "number"
        ? point.cadenceCyclesPerMin
        : undefined,
    powerWatts:
      typeof point.powerWatts === "number" ? point.powerWatts : undefined,
    time: point.dateTime ?? point.reportedTime,
    distanceMeters:
      typeof point.totalDistanceMeters === "number"
        ? point.totalDistanceMeters
        : typeof point.distanceMeters === "number"
          ? point.distanceMeters
          : undefined,
    durationSecs:
      typeof point.totalDurationSecs === "number"
        ? point.totalDurationSecs
        : typeof point.durationSecs === "number"
          ? point.durationSecs
          : undefined,
  };
}

function buildRouteSummary(
  points: GarminTrackPoint[],
  session: GarminSessionData,
): {
  totalDistanceMeters?: number;
  totalDurationSecs?: number;
  lastReportedTime?: string;
  pointCount: number;
  isActive: boolean;
} {
  const lastPoint = points.at(-1);
  const lastReportedTime = lastPoint?.time;
  return {
    pointCount: points.length,
    totalDistanceMeters: lastPoint?.distanceMeters,
    totalDurationSecs: lastPoint?.durationSecs,
    lastReportedTime,
    isActive: isSessionActive(session, lastReportedTime),
  };
}

function isSessionActive(
  session: GarminSessionData,
  lastReportedTime?: string,
): boolean {
  const extractedAtMs = Date.now();
  const startMs = session.start ? Date.parse(session.start) : Number.NaN;
  const endMs = session.end ? Date.parse(session.end) : Number.NaN;
  const lastReportedMs = lastReportedTime
    ? Date.parse(lastReportedTime)
    : Number.NaN;
  if ([startMs, endMs, lastReportedMs].some((value) => Number.isNaN(value)))
    return false;
  const frequencySecs =
    typeof session.postTrackPointFrequency === "number"
      ? session.postTrackPointFrequency
      : 15;
  const freshnessWindowMs = Math.max(frequencySecs * 8_000, 10 * 60_000);
  return (
    extractedAtMs >= startMs &&
    extractedAtMs <= endMs + freshnessWindowMs &&
    extractedAtMs - lastReportedMs <= freshnessWindowMs
  );
}
