import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  getDailyLog,
  saveDailyLog,
  listDailyLogs,
  copyDay,
  deleteDailyLog,
} from "./dailyLog";

function mockFetch(body: unknown, status = 200) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(body), { status }));
}

describe("dailyLog API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("getDailyLog fetches correct URL", async () => {
    const spy = mockFetch({ date: "2024-01-01", caffeine_entries: [] });
    await getDailyLog("2024-01-01");
    expect(spy).toHaveBeenCalledWith(
      "/api/daily-log/2024-01-01",
      expect.anything(),
    );
  });

  it("saveDailyLog sends PUT with body", async () => {
    const spy = mockFetch({ data: { date: "2024-01-01" }, warnings: [] });
    await saveDailyLog("2024-01-01", {
      is_sick: null,
      notes: null,
      caffeine_entries: [],
      meal_entries: [],
      supplement_entries: [],
      habit_entries: [],
      stimulating_activity_entries: [],
      sexual_activity_entry: null,
      pre_bed_ritual_entries: [],
      nap_entries: [],
      sunlight_entries: [],
      red_light_entries: [],
      nsdr_entries: [],
      section_absences: [],
    });
    expect(spy).toHaveBeenCalledWith(
      "/api/daily-log/2024-01-01",
      expect.objectContaining({
        method: "PUT",
      }),
    );
  });

  it("listDailyLogs with no params", async () => {
    const spy = mockFetch([]);
    await listDailyLogs();
    expect(spy).toHaveBeenCalledWith("/api/daily-log", expect.anything());
  });

  it("listDailyLogs with date range", async () => {
    const spy = mockFetch([]);
    await listDailyLogs("2024-01-01", "2024-01-31");
    expect(spy).toHaveBeenCalledWith(
      "/api/daily-log?start_date=2024-01-01&end_date=2024-01-31",
      expect.anything(),
    );
  });

  it("copyDay sends POST", async () => {
    const spy = mockFetch({ date: "2024-01-02" });
    await copyDay("2024-01-02", "2024-01-01");
    expect(spy).toHaveBeenCalledWith(
      "/api/daily-log/2024-01-02/copy-from/2024-01-01",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("deleteDailyLog sends DELETE", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));
    await deleteDailyLog("2024-01-01");
    expect(spy).toHaveBeenCalledWith(
      "/api/daily-log/2024-01-01",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
