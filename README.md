# Script Juggler

**Script Juggler** is a floating workflow manager for [Glyphs.app](https://glyphsapp.com). It lets you collect any subset of your installed Glyphs scripts into an ordered list, run them one by one (or selectively), mark them done, and save the whole setup as a reusable preset—all without leaving Glyphs.


## Installation

Look for *Script Juggler* in *Window > Plugin Manager > Scripts,* then click the *Install* button next to it. Once you are done, hold down the Opt key and choose *Script > Reload Scripts* (Cmd-Opt-Shift-Y).


## Opening the window

Run **Script Juggler** from the Glyphs *Script* menu. The window is non-modal and can stay open while you work. You can run the script a second time to open a second, independent window—each window maintains its own list.


## The main window

```
   #  ●  Script Name              ▶ 
┌────────────────────────────────────┐
│  1  ○  Check Glyph Names        ▶  │
│  2  ●  Decompose Compounds      ▶  │
│  3  ○  Remove Overlap           ▶  │
│  4  ○  Rename Glyphs            ▶  │
├────────────────────────────────────┤
│  …  ↺                           +  │
└────────────────────────────────────┘
```

Each row has four columns:

| Column | Contents | Purpose |
|--------|----------|---------|
| **#** (number) | Row position | Drag handle for manual reordering |
| **Ring** | Status indicator | Shows done / played state (see below) |
| **Title** | Script name | Hover to see full path; double-click to run |
| **▶** | Play button | Click to run the script immediately |


## Adding scripts — the Collect dialog

Click the **plus button** at the bottom right to open the *Collect* dialog. This dialog lists every script in your Glyphs Scripts folder that has a `# MenuTitle:` declaration.


## The ring indicator

The ring in the second column communicates two independent states at a glance:

| Appearance | Meaning |
|------------|---------|
| 🔘 — empty grey circle | Marked as **not done** |
| 🟢 — solid green circle | Marked as **done** |
| extra dot inside circle | **has been run** at least once this session |

"Done" is a manual flag you set to track your progress through the workflow. "Played" is set automatically when a script has been executed—it resets each time you close and reopen the window.

Hover over the ring column header to see a quick-reference tooltip.


## Running scripts

There are three ways to run a script:

- **Click the ▶ button** in the play column of any row.
- **Double-click the script title**.
- **Press Return or Enter** when exactly one row is selected.

After a script runs, its ring gains an inner dot to show it was played this session. Errors are reported in the Glyphs Macro Window, which opens automatically on failure.


## Marking scripts done

There are two ways to toggle the "done" flag:

- **Click the ring** (○/●) to toggle that single row.
- **Press Space** to toggle all currently selected rows at once.

Done status is saved automatically and restored when you reopen the window.


## Keyboard navigation

When the script list has keyboard focus (click any row to give it focus):

| Key | Action |
|-----|--------|
| `↑` / `↓` | Select previous/next script |
| `Shift ↑` / `Shift ↓` | Extend selection up/down |
| `Opt ↑` / `Opt ↓` | Select first/last script |
| `Cmd ↑` / `Cmd ↓` | Move selected script(s) **one position up** / **down** |
| `Cmd Opt ↑` / `Cmd Opt ↓` | Move selected script(s) to the very **top** / **bottom** |
| `Space` | Toggle done status for all selected rows |
| `Return` or `Enter` | Run the selected script (only when one row is selected) |
| `Delete` or `Backspace` | Remove selected row(s) from the list |

When moving multiple rows, their relative order is preserved. The selection moves with the rows.


## Selecting rows

Script Juggler uses standard macOS list selection:

| Gesture | Result |
|---------|--------|
| **Click** a row | Select that row exclusively |
| **Shift-click** | Extend selection to include all rows between the anchor and the clicked row |
| **Cmd-click** | Add or remove a single row from the current selection |
| **Click empty space** | Deselect all |

Multiple selected rows can be moved, toggled done, deleted, or dragged all at once.


## Drag-to-reorder

Rows can be reordered by dragging. Only the **number column (#)** is the drag handle—clicking there starts a drag without changing the selection.

**To drag one row:**

1. Click and hold the **number** at the left edge of any row.
2. Drag up or down. A **thin blue line** appears between rows to show where the row will be inserted.
3. A **semi-transparent ghost image** of the dragged row(s) follows the cursor.
4. Release to drop the row at the indicated position.

**To drag multiple rows:**

1. First, select the rows you want to move (Shift-click or Cmd-click).
2. Click and hold the **number** of any row that is selected.
3. All selected rows are moved together as a group, keeping their relative order.
4. Release to drop them at the blue line.

If you click the number of an *unselected* row, only that single row is dragged regardless of the current selection.

### Searching

The search field supports:

- **Multiple terms** (space-separated) — all terms must match (AND logic).
- **Wildcards** — `*` matches any sequence of characters, `?` matches exactly one.
- **Quoted phrases** — surround a multi-word phrase in double quotes for a literal match: `"check glyph"`.

The list filters in real time as you type.

### Selecting and collecting

- **Click** to select a script.
- **Shift-click** or **Cmd-click** to select multiple scripts.
- **Double-click** a script or press **Return** (or click **Collect**) to add the selection to the juggler.

Scripts are inserted immediately after the last selected row in the main list (or appended at the end if nothing is selected). Duplicates are silently skipped.

Hovering over any script in the list shows its `__doc__` string as a tooltip, so you can read a short description before adding it.


## Removing scripts from the list

Select one or more rows and press `Delete` or `Backspace`. The entries are removed from the list and the **↺ undo button** appears at the bottom left.

The **↺ button** (bottom left, shown only after a deletion or clear) restores the entire list to the state it was in just before the last destructive action. Only the most recent operation can be undone; once you undo, the button disappears.


## The Actions menu (⋯)

Click the **⋯ button** at the bottom left to open the actions menu:

| Item | What it does |
|------|--------------|
| **Save Preset** | Saves the current list to a `.plist` file. The save dialog defaults to the folder of the frontmost open font file. |
| **Load Preset** | Opens a `.plist` file and replaces the current list. Done flags are restored; played-this-session state is reset. |
| **Clear List** | Removes all rows. The ↺ undo button appears so you can recover the list if needed. |


### Preset files

Presets are standard XML property-list (`.plist`) files and can be shared between machines. They store each script's file path, display title, and done state. If a preset references a script that no longer exists at the saved path, that entry will still appear in the list—it will just fail to run with a message in the Macro Window.


## Auto-save and persistence

The list is saved automatically to Glyphs' persistent preferences on every change. When you run Script Juggler again, it restores the list exactly as you left it—including which scripts are marked done.

Each open Script Juggler window saves its contents independently (keyed by window order). If you run Script Juggler twice, each window remembers its own list across sessions.


---

## Tips

- **Workflow order:** Arrange scripts in the exact order you plan to run them. Use the keyboard shortcuts or drag-and-drop to tune the order without touching the mouse.
- **Track progress:** Mark scripts done as you work through a checklist. The green ring gives you an instant overview of what remains.
- **Revisit played scripts:** The inner dot shows which scripts were already run this session even if you haven't marked them done—useful when iterating on a script multiple times.
- **Project-specific presets:** Save a preset per font project (next to the `.glyphs` file) so you can load exactly the right workflow for each job.
- **Search shortcuts:** In the Collect dialog, type the folder name to narrow down by category, e.g. `metrics` or `kerning "check pairs"`.
