# Part master import from Excel

The workspace **Parts** page can build the same structure as `fir_part_master_bundle_v1` JSON from a multi-sheet `.xlsx` workbook, then save dimensions (A), complaints (B), material (C), and coating (D) into the database.

## Template

Click **Download Excel template** on `/workspace/parts`. You get:

| Sheet       | Purpose | Columns |
|------------|---------|---------|
| **Parts**  | One row per part | Part Number, Drawing Rev, Description |
| **Section_A** | Dimension parameters (A) | Part Number, Parameter, Specification, Special Char, Method of Inspection |
| **Section_B** | Customer complaint parameters (B) | Same as A |
| **Section_C** | Material grades (C) | Part Number, Material Grade |
| **Section_D** | Coating (D) | Same as A |

Sheet names are matched **case-insensitively**. Aliases are accepted, e.g. `A`, `Dimensions`, `B`, `CCP`, `C`, `Material`, `D`, `Coating`.

## Column headers

Headers are normalized (spaces/case). Examples:

- Part number: `Part Number`, `Part No`, `Part`
- Drawing rev: `Drawing Rev`, `Revision`, `Rev`, `Draw. Rev No` (FIR-style)
- A/B/D rows: `Parameter`, `Specification`, `Specification (mm)`, `Special Char`, `Special Characteristics`, `Method of Inspection` (or `Method`)
- Material: `Material Grade`, `Grade`

Rows with an empty **Parameter** (A/B/D) are skipped. Rows with an empty **Material Grade** (C) are skipped.

## Flow

1. **Upload Excel (review before save)** — calls `POST /api/app/parts/preview-excel-master` (no DB change). The UI shows part header + Section A–D tables; **OK** posts the same JSON to `POST /api/app/parts/import-bundle` (same upsert as JSON import).
2. **API-only direct import** — `POST /api/app/parts/import-excel-master` parses and writes in one step (no review screen).

## FIR-style workbooks (single sheet)

If the file is **not** using the template sheet names, the parser runs a second pass on the raw grid:

- Looks for labels **Part No**, **Part Number**, **Description**, **Draw. Rev No** (value to the right or in the cell below).
- Finds a **header row** that includes both **Parameter** and **Specification**, then reads dimension rows until a run of blank parameters.
- If the part number is not in the grid but the **sheet tab name** looks like a part code (e.g. `B1V24302`, not `Sheet1`), that name is used when the sheet has a parameter table or material lines.
- If the grid still has no part number, the **uploaded file name** (without extension) is used when it looks like a part code — e.g. uploading `B1V24302.xlsx` can set part `B1V24302` when the workbook has a dimension table but no Part No cell.
- Rows whose parameter suggests **coating / powder / DFT** are mapped to **Section D** (`coating_rows`); the rest go to **Section A** (`spec_rows`).

For best results, either use the downloadable template or ensure **Part No** and the dimension table headers are present.

## Notes

- Part master stores **specification / method / special char** for A–D — not invoice, lot qty, or measured-value columns from a paper FIR. Map those into the template columns above if you need them in master data.
- **`.xlsx` recommended**; `.xls` may work if your Python stack has the right engine.
- Part numbers are **trimmed**; the same part in **Parts** and section sheets is merged.
- You can omit the **Parts** sheet if every part appears on at least one section sheet (meta rev/description may be empty).
- Empty template (headers only) previews as `{ "parts": [] }`.
