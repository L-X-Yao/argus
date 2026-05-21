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

const DB_KEY = 'pllink_flights';

export function saveFlightRecord(record: Omit<FlightRecord, 'id'>): void {
  const records = loadFlightRecords();
  const id = records.length > 0 ? Math.max(...records.map(r => r.id)) + 1 : 1;
  records.push({ ...record, id });
  if (records.length > 200) records.splice(0, records.length - 200);
  try { localStorage.setItem(DB_KEY, JSON.stringify(records)); } catch {}
}

export function loadFlightRecords(): FlightRecord[] {
  try {
    return JSON.parse(localStorage.getItem(DB_KEY) || '[]');
  } catch { return []; }
}

export function deleteFlightRecord(id: number): void {
  const records = loadFlightRecords().filter(r => r.id !== id);
  try { localStorage.setItem(DB_KEY, JSON.stringify(records)); } catch {}
}
