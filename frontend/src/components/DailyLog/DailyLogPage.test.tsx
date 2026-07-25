import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DailyLogPage } from "./DailyLogPage";
import { addDays, todayStr } from "../../utils/date";

const mockLogOut = {
  date: "2024-06-15",
  copied_from_date: null,
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
};

const mockSettings = {
  oura_token_set: false,
  typical_bedtime: "22:30:00",
  target_wake_time: "06:30:00",
  caffeine_sensitivity: "normal",
  timezone: "America/New_York",
  chronotype: "intermediate",
  zip_code: null,
  age: 30,
  display_mode: "circadian",
  circadian_mode_start: "20:00:00",
  onboarding_completed: true,
};

function mockFetch(
  log: Record<string, unknown> = mockLogOut,
  products: unknown[] = [],
) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/api/settings")) {
      return new Response(JSON.stringify(mockSettings));
    }
    if (urlStr.includes("/api/supplement-products")) {
      return new Response(JSON.stringify(products));
    }
    if (
      urlStr.includes("/api/daily-log/") &&
      (!init || !init.method || init.method === "GET")
    ) {
      return new Response(JSON.stringify(log));
    }
    if (urlStr.includes("/api/daily-log/") && init?.method === "PUT") {
      // Echo the payload like the real backend does — a canned response
      // would silently reset the form and mask round-trip bugs.
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      return new Response(
        JSON.stringify({ data: { ...log, ...body }, warnings: [] }),
      );
    }
    if (urlStr.includes("/api/red-light-panels")) {
      return new Response(JSON.stringify([]));
    }
    return new Response(JSON.stringify({ detail: "Not found" }), {
      status: 404,
    });
  });
}

/** The body of the most recent PUT to the daily-log endpoint. */
function lastPutBody(): Record<string, unknown> {
  const calls = vi.mocked(globalThis.fetch).mock.calls;
  const puts = calls.filter(
    ([, init]) => init && (init as RequestInit).method === "PUT",
  );
  expect(puts.length).toBeGreaterThan(0);
  const [, init] = puts[puts.length - 1];
  return JSON.parse(String((init as RequestInit).body)) as Record<
    string,
    unknown
  >;
}

function renderPage(date = "2024-06-15") {
  return render(
    <MemoryRouter initialEntries={[`/log/${date}`]}>
      <Routes>
        <Route path="/log/:date" element={<DailyLogPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DailyLogPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders date navigator", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Jun/)).toBeInTheDocument();
    });
  });

  it("renders section headers", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Caffeine")).toBeInTheDocument();
    });
    expect(screen.getByText("Meals")).toBeInTheDocument();
    expect(screen.getByText("Supplements")).toBeInTheDocument();
    expect(screen.getByText("Habits")).toBeInTheDocument();
  });

  it("shows save button", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });
  });

  it("calls PUT on save", async () => {
    mockFetch();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Save"));
    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls;
      const putCall = calls.find(
        ([, init]) => init && (init as RequestInit).method === "PUT",
      );
      expect(putCall).toBeDefined();
    });
  });

  it("shows loading initially", () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders copy day button", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Copy from another day")).toBeInTheDocument();
    });
  });

  it("renders notes textarea", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText("Any other notes about today..."),
      ).toBeInTheDocument();
    });
  });

  // --- #35: explicit save feedback + load-failure guard ---

  it("shows Saved ✓ after a successful save and clears it on edit", async () => {
    mockFetch();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Save"));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved ✓");

    // Any edit invalidates the confirmation
    await user.click(screen.getByLabelText("Sick day"));
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  it("surfaces a failed save with the backend detail", async () => {
    mockFetch();
    vi.mocked(globalThis.fetch).mockImplementation(async (url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      if (urlStr.includes("/api/daily-log/") && init?.method === "PUT") {
        return new Response(
          JSON.stringify({ detail: "red-light panel 7 does not exist" }),
          { status: 409 },
        );
      }
      return new Response(JSON.stringify(mockLogOut));
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Save"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Save failed: red-light panel 7 does not exist",
    );
    // Form is still there — nothing lost
    expect(screen.getByText("Caffeine")).toBeInTheDocument();
  });

  it("falls back to a generic message when a 422 detail is not a string", async () => {
    mockFetch();
    vi.mocked(globalThis.fetch).mockImplementation(async (url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      if (urlStr.includes("/api/daily-log/") && init?.method === "PUT") {
        // FastAPI validation errors carry an array in detail
        return new Response(
          JSON.stringify({
            detail: [{ loc: ["body", "caffeine_entries"], msg: "bad" }],
          }),
          { status: 422 },
        );
      }
      return new Response(JSON.stringify(mockLogOut));
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Save"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Save failed (HTTP 422)",
    );
  });

  it("shows an error panel instead of an empty form when loading fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      return new Response(JSON.stringify({ detail: "boom" }), { status: 500 });
    });
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Loading this day failed: boom",
    );
    // The overwrite hazard: no editable form, no Save button
    expect(screen.queryByText("Save")).not.toBeInTheDocument();
    expect(screen.queryByText("Caffeine")).not.toBeInTheDocument();
  });

  it("retry after a failed load fetches the day again", async () => {
    let failGet = true;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      if (
        urlStr.includes("/api/daily-log/") &&
        (!init || !init.method || init.method === "GET")
      ) {
        if (failGet) {
          return new Response(JSON.stringify({ detail: "boom" }), {
            status: 500,
          });
        }
        return new Response(JSON.stringify(mockLogOut));
      }
      return new Response(JSON.stringify([]));
    });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    failGet = false;
    await user.click(screen.getByText("Retry"));
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });
    expect(screen.getByText("Caffeine")).toBeInTheDocument();
  });

  // --- #47: tracked-sections gating ---

  it("hides untracked sections without data", async () => {
    localStorage.setItem(
      "somnus-tracked-sections",
      JSON.stringify(["caffeine", "meals"]),
    );
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Caffeine")).toBeInTheDocument();
    });
    expect(screen.getByText("Meals")).toBeInTheDocument();
    expect(screen.queryByText("Supplements")).not.toBeInTheDocument();
    expect(screen.queryByText("Naps")).not.toBeInTheDocument();
    expect(screen.queryByText("NSDR")).not.toBeInTheDocument();
  });

  it("an untracked section still renders when the day holds data in it", async () => {
    localStorage.setItem(
      "somnus-tracked-sections",
      JSON.stringify(["caffeine"]),
    );
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      if (
        urlStr.includes("/api/daily-log/") &&
        (!init || !init.method || init.method === "GET")
      ) {
        return new Response(
          JSON.stringify({
            ...mockLogOut,
            nap_entries: [
              {
                id: 1,
                date: "2024-06-15",
                start_time: "14:00:00",
                end_time: "14:30:00",
                duration_minutes: 30,
              },
            ],
          }),
        );
      }
      return new Response(JSON.stringify([]));
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Caffeine")).toBeInTheDocument();
    });
    expect(screen.getByText("Naps")).toBeInTheDocument(); // has data → shows
    expect(screen.queryByText("Meals")).not.toBeInTheDocument(); // untracked, empty
  });

  it("renders every section when nothing is stored (default all-on)", async () => {
    mockFetch();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Caffeine")).toBeInTheDocument();
    });
    expect(screen.getByText("Supplements")).toBeInTheDocument();
    expect(screen.getByText("Naps")).toBeInTheDocument();
  });

  // --- #159/#161: explicit absence — THE ROUND-TRIP CONTRACT ---
  // The PUT replaces the day's section_absences wholesale, so every save
  // must round-trip the loaded keys or an unrelated edit wipes them.

  it("ROUND-TRIP CONTRACT: saving an unrelated edit keeps the day's absences", async () => {
    mockFetch({ ...mockLogOut, section_absences: ["sauna", "alcohol"] });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    // Edit something unrelated to any absence
    await user.type(
      screen.getByPlaceholderText("Any other notes about today..."),
      "slept fine",
    );
    await user.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(lastPutBody().section_absences).toEqual(["sauna", "alcohol"]);
    });
  });

  it("Mark none today puts the key in the payload; Undo removes it", async () => {
    mockFetch();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    // Caffeine section is open by default
    await user.click(
      screen.getByRole("button", { name: "Mark caffeine none today" }),
    );
    await user.click(screen.getByText("Save"));
    await waitFor(() => {
      expect(lastPutBody().section_absences).toEqual(["caffeine"]);
    });

    await user.click(
      screen.getByRole("button", { name: "Undo — restore caffeine today" }),
    );
    await user.click(screen.getByText("Save"));
    await waitFor(() => {
      expect(lastPutBody().section_absences).toEqual([]);
    });
  });

  it("adding an entry clears that section's absence key", async () => {
    mockFetch({ ...mockLogOut, section_absences: ["caffeine", "sauna"] });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: "Undo — restore caffeine today" }),
    ).toBeInTheDocument();

    await user.click(screen.getByText("+ Espresso (63mg)"));
    await user.click(screen.getByText("Save"));

    await waitFor(() => {
      // caffeine cleared by the new entry; unrelated sauna key survives
      expect(lastPutBody().section_absences).toEqual(["sauna"]);
    });
  });

  it("habit none-today chips toggle their own keys", async () => {
    mockFetch();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Habits")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Habits/ }));
    await user.click(screen.getByRole("button", { name: "No sauna today" }));
    await user.click(screen.getByRole("button", { name: "No alcohol today" }));
    await user.click(screen.getByText("Save"));
    await waitFor(() => {
      expect(lastPutBody().section_absences).toEqual(["sauna", "alcohol"]);
    });
  });

  // --- #161: supplement library integration ---

  const stickyProduct = {
    id: 5,
    name: "Melatonin",
    brand: "NOW",
    form: null,
    default_dose: 3,
    unit: "mg",
    step: 0.5,
    is_sticky: true,
  };

  it("sticky products auto-populate a not-yet-saved TODAY at the default dose", async () => {
    localStorage.setItem("somnus-section-supplements", "true");
    const today = todayStr();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      if (urlStr.includes("/api/supplement-products")) {
        return new Response(JSON.stringify([stickyProduct]));
      }
      if (urlStr.includes("/api/daily-log/") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return new Response(
          JSON.stringify({
            data: { ...mockLogOut, date: today, ...body },
            warnings: [],
          }),
        );
      }
      // No log exists yet for the day
      return new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
      });
    });
    const user = userEvent.setup();
    renderPage(today);

    const dose = await screen.findByRole("spinbutton", {
      name: "Melatonin dose (mg)",
    });
    expect(dose).toHaveValue(3);

    // Being listed = took@default: the row rides the save payload
    await user.click(screen.getByText("Save"));
    await waitFor(() => {
      expect(lastPutBody().supplement_entries).toEqual([
        { time: null, name: "Melatonin", dose_mg: 3, product_id: 5 },
      ]);
    });
  });

  it("sticky products do NOT populate a blank past day", async () => {
    localStorage.setItem("somnus-section-supplements", "true");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      if (urlStr.includes("/api/supplement-products")) {
        return new Response(JSON.stringify([stickyProduct]));
      }
      return new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
      });
    });
    renderPage("2024-06-15");

    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("spinbutton", { name: "Melatonin dose (mg)" }),
    ).not.toBeInTheDocument();
  });

  it("copy-yesterday pulls yesterday's supplement rows into the form", async () => {
    localStorage.setItem("somnus-section-supplements", "true");
    const yesterday = addDays("2024-06-15", -1);
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/api/settings")) {
        return new Response(JSON.stringify(mockSettings));
      }
      if (urlStr.includes("/api/supplement-products")) {
        return new Response(JSON.stringify([stickyProduct]));
      }
      if (urlStr.includes(`/api/daily-log/${yesterday}`)) {
        return new Response(
          JSON.stringify({
            ...mockLogOut,
            date: yesterday,
            supplement_entries: [
              {
                id: 11,
                date: yesterday,
                time: "21:30:00",
                name: "Melatonin",
                dose_mg: 2.5,
                product_id: 5,
              },
            ],
          }),
        );
      }
      if (urlStr.includes("/api/daily-log/2024-06-15")) {
        return new Response(JSON.stringify(mockLogOut));
      }
      return new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
      });
    });
    const user = userEvent.setup();
    renderPage("2024-06-15");
    await waitFor(() => {
      expect(screen.getByText("Save")).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: "Copy yesterday's supplements" }),
    );

    expect(
      await screen.findByRole("spinbutton", { name: "Melatonin dose (mg)" }),
    ).toHaveValue(2.5);
    expect(screen.getByLabelText("Melatonin time")).toHaveDisplayValue("21:30");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Copied 1 supplement from yesterday",
    );
  });
});
