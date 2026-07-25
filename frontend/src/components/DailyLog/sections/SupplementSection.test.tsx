import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { SupplementSection } from "./SupplementSection";
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
}

function Harness({
  initial = [],
  products = [melatonin, magnesium],
  onCreateProduct = vi.fn(),
}: HarnessProps) {
  const [entries, setEntries] = useState(initial);
  return (
    <SupplementSection
      entries={entries}
      onChange={setEntries}
      products={products}
      onCreateProduct={onCreateProduct}
    />
  );
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
    const onCreateProduct = vi.fn(async () => created);
    render(<Harness onCreateProduct={onCreateProduct} />);

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

  it("Mark all none today zeroes every listed row", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[
          melatoninRow(3),
          {
            time: null,
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
    // All rows at 0 → nothing left to mark
    expect(
      screen.queryByRole("button", { name: "Mark all none today" }),
    ).not.toBeInTheDocument();
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
