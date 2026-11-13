export interface FlightRecord {
  id: number;
  date: string;
  duration: number;
  maxAlt: number;
  maxSpeed: number;
  totalDist: number;
  batUsed: number;
  vtype: string;
  fw: string;
  eventCount: number;
}

const DB_KEY = 'argus_flights';

export function saveFlightRecord(record: Omit<FlightRecord, 'id'>): void {
  const records = loadFlightRecords();
  // Two pages of one operator record the same flight from the same summary; a few seconds
  // apart their records match field for field, and one flight must not show twice.
  const at = Date.parse(record.date);
  const twin = records.find(
    (r) =>
      r.duration === record.duration &&
      r.maxAlt === record.maxAlt &&
      r.maxSpeed === record.maxSpeed &&
      r.totalDist === record.totalDist &&
      r.batUsed === record.batUsed &&
      Math.abs(Date.parse(r.date) - at) < 5000,
  );
  if (twin) return;
  const id = records.length > 0 ? Math.max(...records.map((r) => r.id)) + 1 : 1;
  records.push({ ...record, id });
  if (records.length > 200) records.splice(0, records.length - 200);
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(records));
  } catch {}
}

export function loadFlightRecords(): FlightRecord[] {
  try {
    const data = JSON.parse(localStorage.getItem(DB_KEY) || '[]');
    // The next id is worked out from these, on the way in of a state message from the backend.
    return Array.isArray(data) ? data.filter((r) => r && typeof r.id === 'number' && Number.isFinite(r.id)) : [];
  } catch {
    return [];
  }
}

export function deleteFlightRecord(id: number): void {
  const records = loadFlightRecords().filter((r) => r.id !== id);
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(records));
  } catch {}
}
