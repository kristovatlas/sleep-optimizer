import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { SupplementSection } from "./SupplementSection";
import { rowForProduct } from "./supplementRow";
import type {
  SupplementEntryCreate,
  SupplementProduct,
  SupplementProductCreate,
} from "../../../types";

const melatonin: SupplementProduct = {
  id: 1,
  name: "Melatonin",
  brand: "NOW",
  form: "sublingual",
  default_dose: 3,
  unit: "mg",
  step: 0.5,
  is_sticky: false,
};

const magnesium: SupplementProduct = {
  id: 2,
  name: "Magnesium Glycinate",
  brand: "Pure Encapsulations",
  form: null,
  default_dose: 200,
  unit: "mg",
  step: 50,
  is_sticky: true,
};

function melatoninRow(dose: number | null = 3): SupplementEntryCreate {
  return { time: null, name: "Melatonin", dose_mg: dose, product_id: 1 };
}

interface HarnessProps {
  initial?: SupplementEntryCreate[];
  products?: SupplementProduct[] | null;
  onCreateProduct?: (
    data: SupplementProductCreate,
  ) => Promise<SupplementProduct>;
  onCopyYesterday?: () => Promise<number | null>;
}

function Harness({
  initial = [],
  products = [melatonin, magnesium],
  onCreateProduct = vi.fn(),
  onCopyYesterday = vi.fn(async () => 0),
}: HarnessProps) {
  const [entries, setEntries] = useState(initial);
  return (
    <SupplementSection
      entries={entries}
      onChange={setEntries}
      products={products}
      onCreateProduct={onCreateProduct}
      onCopyYesterday={onCopyYesterday}
    />
  );
}

/** Render with a spy onChange to assert the exact emitted payload. */
function renderSpy(
  entries: SupplementEntryCreate[],
  products: SupplementProduct[] | null = [melatonin, magnesium],
) {
  const onChange = vi.fn();
  render(
    <SupplementSection
      entries={entries}
      onChange={onChange}
      products={products}
      onCreateProduct={vi.fn()}
      onCopyYesterday={vi.fn(async () => 0)}
    />,
  );
  return onChange;
}

describe("SupplementSection", () => {
  beforeEach(() => {
    localStorage.clear();
    // Section open by default for the tests
    localStorage.setItem("somnus-section-supplements", "true");
  });

  it("renders a product-linked row with name, meta, and unit", () => {
    render(<Harness initial={[melatoninRow()]} />);
    expect(screen.getByText("Melatonin")).toBeInTheDocument();
    expect(screen.getByText("NOW · sublingual")).toBeInTheDocument();
    expect(screen.getByText("mg")).toBeInTheDocument();
    expect(
      screen.getByRole("spinbutton", { name: "Melatonin dose (mg)" }),
    ).toHaveValue(3);
  });

  it("dose 0 IS the none-today state; a positive dose clears it", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[melatoninRow()]} />);
    const dose = screen.getByRole("spinbutton", {
      name: "Melatonin dose (mg)",
    });

    await user.clear(dose);
    await user.type(dose, "0");
    expect(screen.getByText("none today")).toBeInTheDocument();

    await user.clear(dose);
    await user.type(dose, "2.5");
    expect(screen.queryByText("none today")).not.toBeInTheDocument();
    expect(dose).toHaveValue(2.5);
  });

  it("+/− nudge by the product's step and − clamps at 0", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[melatoninRow(0.5)]} />);
    const dose = screen.getByRole("spinbutton", {
      name: "Melatonin dose (mg)",
    });

    await user.click(
      screen.getByRole("button", { name: "Increase Melatonin dose" }),
    );
    expect(dose).toHaveValue(1);

    const dec = screen.getByRole("button", { name: "Decrease Melatonin dose" });
    await user.click(dec);
    await user.click(dec);
    expect(dose).toHaveValue(0);
    await user.click(dec);
    expect(dose).toHaveValue(0); // clamped — never negative
    expect(screen.getByText("none today")).toBeInTheDocument();
  });

  it("the × button removes the row entirely (not recorded)", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[melatoninRow()]} />);
    await user.click(screen.getByRole("button", { name: "Remove Melatonin" }));
    expect(screen.queryByText("Melatonin")).not.toBeInTheDocument();
  });

  it("time chip sets and clears the per-entry time", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[melatoninRow()]} />);

    await user.click(
      screen.getByRole("button", { name: "Set Melatonin time" }),
    );
    const time = screen.getByLabelText("Melatonin time");
    expect(time).toHaveDisplayValue(/^\d{2}:\d{2}$/);

    await user.click(
      screen.getByRole("button", { name: "Clear Melatonin time" }),
    );
    expect(screen.queryByLabelText("Melatonin time")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Set Melatonin time" }),
    ).toBeInTheDocument();
  });

  it("adds a row from the library picker with type-to-filter", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(
      screen.getByRole("button", { name: "+ Add a supplement" }),
    );
    await user.type(
      screen.getByLabelText("Search supplement library"),
      "magnes",
    );
    expect(screen.queryByText("Melatonin")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: /Magnesium Glycinate/ }),
    );

    // Row prefilled at the library default dose, no time
    expect(
      screen.getByRole("spinbutton", { name: "Magnesium Glycinate dose (mg)" }),
    ).toHaveValue(200);
    expect(
      screen.getByRole("button", { name: "Set Magnesium Glycinate time" }),
    ).toBeInTheDocument();
  });

  it("inline-creates a product then adds its row", async () => {
    const user = userEvent.setup();
    const created: SupplementProduct = {
      id: 9,
      name: "Apigenin",
      brand: null,
      form: null,
      default_dose: 50,
      unit: "mg",
      step: 0.5,
      is_sticky: false,
    };
    const onCreateProduct = vi.fn(async (data: SupplementProductCreate) => ({
      ...created,
      name: data.name,
    }));
    // Owner harness mimicking DailyLogPage: the row append rides
    // onCreateProduct as a FUNCTIONAL update after the POST resolves —
    // the section itself never appends from a pre-await entries snapshot.
    function OwnerHarness() {
      const [entries, setEntries] = useState<SupplementEntryCreate[]>([]);
      return (
        <SupplementSection
          entries={entries}
          onChange={setEntries}
          products={[melatonin, magnesium]}
          onCreateProduct={async (data) => {
            const p = await onCreateProduct(data);
            setEntries((prev) => [...prev, rowForProduct(p)]);
            return p;
          }}
          onCopyYesterday={vi.fn(async () => 0)}
        />
      );
    }
    render(<OwnerHarness />);

    await user.click(
      screen.getByRole("button", { name: "+ Add a supplement" }),
    );
    await user.click(screen.getByRole("button", { name: "+ New product" }));
    expect(
      screen.getByRole("button", { name: "Add to library" }),
    ).toBeDisabled(); // name is required
    await user.type(screen.getByLabelText("New product name"), "Apigenin");
    await user.type(screen.getByLabelText("New product default dose"), "50");
    await user.click(screen.getByRole("button", { name: "Add to library" }));

    await waitFor(() => {
      expect(
        screen.getByRole("spinbutton", { name: "Apigenin dose (mg)" }),
      ).toHaveValue(50);
    });
    expect(onCreateProduct).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Apigenin",
        default_dose: 50,
        unit: "mg",
        is_sticky: false,
      }),
    );
  });

  it("surfaces a failed product create without adding a row", async () => {
    const user = userEvent.setup();
    const onCreateProduct = vi.fn(async () => {
      throw new Error("boom");
    });
    render(<Harness onCreateProduct={onCreateProduct} />);

    await user.click(
      screen.getByRole("button", { name: "+ Add a supplement" }),
    );
    await user.click(screen.getByRole("button", { name: "+ New product" }));
    await user.type(screen.getByLabelText("New product name"), "Apigenin");
    await user.click(screen.getByRole("button", { name: "Add to library" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't create the product",
    );
    expect(
      screen.queryByRole("spinbutton", { name: "Apigenin dose (mg)" }),
    ).not.toBeInTheDocument();
  });

  it("copy-yesterday chip reports what it pulled", async () => {
    const user = userEvent.setup();
    const onCopyYesterday = vi.fn(async () => 2);
    render(<Harness onCopyYesterday={onCopyYesterday} />);

    await user.click(
      screen.getByRole("button", { name: "Copy yesterday's supplements" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Copied 2 supplements from yesterday",
    );
    expect(onCopyYesterday).toHaveBeenCalledOnce();
  });

  it("copy-yesterday with nothing logged says so", async () => {
    const user = userEvent.setup();
    render(<Harness onCopyYesterday={vi.fn(async () => 0)} />);
    await user.click(
      screen.getByRole("button", { name: "Copy yesterday's supplements" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "No supplements logged yesterday",
    );
  });

  it("a stale (null) copy-yesterday result shows no status message", async () => {
    const user = userEvent.setup();
    const onCopyYesterday = vi.fn(async () => null);
    render(<Harness onCopyYesterday={onCopyYesterday} />);
    await user.click(
      screen.getByRole("button", { name: "Copy yesterday's supplements" }),
    );
    await waitFor(() => expect(onCopyYesterday).toHaveBeenCalledOnce());
    // null = the user left the day mid-request; a "Copied"/"No supplements"
    // status here would claim an outcome for a day the copy never touched.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("Mark all none today zeroes every product row AND clears their times", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[
          { ...melatoninRow(3), time: "21:30:00" },
          {
            time: "22:00:00",
            name: "Magnesium Glycinate",
            dose_mg: 200,
            product_id: 2,
          },
        ]}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Mark all none today" }),
    );
    expect(screen.getAllByText("none today")).toHaveLength(2);
    expect(
      screen.getByRole("spinbutton", { name: "Melatonin dose (mg)" }),
    ).toHaveValue(0);
    expect(
      screen.getByRole("spinbutton", { name: "Magnesium Glycinate dose (mg)" }),
    ).toHaveValue(0);
    // A 0-dose row must not keep a time — it would fabricate a timing sample
    expect(screen.queryByLabelText("Melatonin time")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Magnesium Glycinate time"),
    ).not.toBeInTheDocument();
    // All rows at 0 → nothing left to mark
    expect(
      screen.queryByRole("button", { name: "Mark all none today" }),
    ).not.toBeInTheDocument();
  });

  it("Mark all none today leaves legacy free-text rows untouched", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[
          melatoninRow(3),
          { time: null, name: "Mystery blend", dose_mg: 100, product_id: null },
        ]}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Mark all none today" }),
    );
    // Only the product-linked row is marked; 0 on an unlinked row would
    // carry no analysis meaning
    expect(screen.getAllByText("none today")).toHaveLength(1);
    expect(
      screen.getByRole("spinbutton", { name: "Mystery blend dose (mg)" }),
    ).toHaveValue(100);
  });

  it("Mark all none today is not offered when only free-text rows hold doses", () => {
    render(
      <Harness
        initial={[
          { time: null, name: "Mystery blend", dose_mg: 100, product_id: null },
        ]}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Mark all none today" }),
    ).not.toBeInTheDocument();
  });

  // --- zero-dose ⇒ no time (a 0-dose row must never feed the Lane-2
  // timing predictor a phantom sample for a product that was not taken) ---

  it("typing dose 0 emits time: null alongside the 0", () => {
    const onChange = renderSpy([{ ...melatoninRow(3), time: "21:30:00" }]);
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Melatonin dose (mg)" }),
      { target: { value: "0" } },
    );
    expect(onChange).toHaveBeenCalledWith([
      { time: null, name: "Melatonin", dose_mg: 0, product_id: 1 },
    ]);
  });

  it("− nudging a dose down to 0 also clears the time", async () => {
    const user = userEvent.setup();
    const onChange = renderSpy([{ ...melatoninRow(0.5), time: "21:30:00" }]);
    await user.click(
      screen.getByRole("button", { name: "Decrease Melatonin dose" }),
    );
    expect(onChange).toHaveBeenCalledWith([
      { time: null, name: "Melatonin", dose_mg: 0, product_id: 1 },
    ]);
  });

  it("re-typing a positive dose after 0 leaves the time cleared", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[{ ...melatoninRow(3), time: "21:30:00" }]} />);
    const dose = screen.getByRole("spinbutton", {
      name: "Melatonin dose (mg)",
    });

    await user.clear(dose);
    await user.type(dose, "0");
    // Time dropped, and a none-today row offers no "+ time" chip either
    expect(screen.queryByLabelText("Melatonin time")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Set Melatonin time" }),
    ).not.toBeInTheDocument();

    await user.clear(dose);
    await user.type(dose, "2");
    // Positive again: time stays cleared (re-settable, never resurrected)
    expect(screen.queryByLabelText("Melatonin time")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Set Melatonin time" }),
    ).toBeInTheDocument();
  });

  it("a typed negative dose is ignored — never clamped into a recorded skip", () => {
    const onChange = renderSpy([melatoninRow(3)]);
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Melatonin dose (mg)" }),
      { target: { value: "-3" } },
    );
    expect(onChange).not.toHaveBeenCalled();
  });

  // --- library fetch failure (products === null) degrades linked rows ---

  it("renders product-linked rows read-only-degraded when the library failed", () => {
    render(
      <Harness
        initial={[
          melatoninRow(3),
          { time: null, name: "Mystery blend", dose_mg: 100, product_id: null },
        ]}
        products={null}
      />,
    );

    // Linked row: stored name as plain text (no editable input), unknown unit
    expect(screen.getByText("Melatonin")).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Supplement 1 name" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Decrease Melatonin dose" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Increase Melatonin dose" }),
    ).toBeDisabled();
    // The typed dose stays editable — it is unit-agnostic on the entry
    expect(
      screen.getByRole("spinbutton", { name: "Melatonin dose (—)" }),
    ).toBeEnabled();

    // Free-text rows never depended on the library: still fully editable
    expect(
      screen.getByRole("textbox", { name: "Supplement 2 name" }),
    ).toHaveValue("Mystery blend");
    expect(
      screen.getByRole("button", { name: "Decrease Mystery blend dose" }),
    ).toBeEnabled();
  });

  it("legacy free-text rows stay editable with an mg unit", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[
          { time: null, name: "Mystery blend", dose_mg: 100, product_id: null },
        ]}
      />,
    );
    const name = screen.getByRole("textbox", { name: "Supplement 1 name" });
    expect(name).toHaveValue("Mystery blend");
    await user.type(name, "!");
    expect(name).toHaveValue("Mystery blend!");
    expect(screen.getByText("mg")).toBeInTheDocument();
  });
});
