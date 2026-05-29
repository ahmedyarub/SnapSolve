# Session Browser

The Session Browser is a full-featured dialog for browsing, reviewing, and organizing past chat sessions.

## Opening the Session Browser

There are two ways to open the Session Browser:

* **Hotkey:** Press `Ctrl + Alt + Shift + B` (configurable in Settings → Keyboard Shortcuts).
* **Control Panel:** Click the **📋 Sessions** button on the floating control panel.

## Interface Layout

The Session Browser opens as a maximized window with a dark theme, divided into two main columns:

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🔍 Filter by tag or session name…                                   │
├────────────────────────┬─────────────────────────────────────────────┤
│                        │  📝 Prompt                                  │
│  Session Tree          │  ─────────────────── (adjustable splitter)  │
│  (left panel)          │  💬 Response                                │
│                        │  (rendered Markdown with syntax highlight)  │
├────────────────────────┴─────────────────────────────────────────────┤
│ Status: 42 sessions • 187 prompts                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### Left Panel — Session Tree

* Sessions are displayed as root items, sorted by date (most recent first).
* Each session shows: `📁 YYYY-MM-DD HH:MM — Session Name [tag1] [tag2]`.
* Under each session, individual prompts are shown as child items with an 100-character excerpt.
* The **latest session is expanded** by default; all others are collapsed.
* Empty sessions (with no interactions) are **automatically filtered out**.
* **Multi-select** is supported: hold `Ctrl` to select individual sessions, or `Shift` to select a range.

### Right Panel — Content Viewer

The right panel is split vertically with an adjustable divider:

* **Top: Prompt** — Shows the full prompt text in a read-only monospace text area.
* **Bottom: Response** — Renders the formatted response using the same engine as the popup (Markdown, LaTeX/KaTeX, Shiki syntax highlighting, and Mermaid diagrams).

### All Splitters Are Adjustable

Both the horizontal (tree vs. content) and vertical (prompt vs. response) dividers can be dragged to resize panels.

## Session Management

### Renaming a Session

1. Right-click on any session in the tree.
2. Select **✏️ Rename Session**.
3. Enter a new name in the dialog.
4. The name persists in the session's JSON file and is shown in the tree.

### Adding Tags

1. Right-click on any session in the tree.
2. Select **🏷️ Edit Tags**.
3. Enter tags as a comma-separated list (e.g., `math, homework, physics`).
4. Tags are displayed as `[tag]` badges after the session name.
5. Tags persist in the session's JSON file.

### Deleting Sessions

1. Select one or more sessions in the tree (use `Ctrl+Click` or `Shift+Click` for multi-select).
2. Either:
   * Right-click and select **🗑️ Delete Session** (or **Delete N Sessions** for multi-select).
   * Press the **Delete** key.
3. Confirm the deletion in the dialog.
4. The session JSON file and any associated captured images are permanently removed.

## Filtering

Use the **filter bar** at the top of the window to search across:

* Session names (custom or auto-generated)
* Session titles
* Tags

Typing in the filter bar instantly filters the tree to show only matching sessions. All matching sessions are automatically expanded when filtering.

## Session Data Format

Sessions are stored as JSON files in the `sessions/` directory. The browser adds two optional fields to the existing format:

```json
{
  "id": "uuid-string",
  "title": "auto-generated title or null",
  "name": "user-defined name or null",
  "tags": ["tag1", "tag2"],
  "updated_at": 1234567890.123,
  "history": [
    {
      "prompt": "user's question",
      "response": "LLM's response",
      "timestamp": "2026-05-29 14:30:00"
    }
  ]
}
```

* `name` — User-defined session name (set via Rename). Defaults to `null`.
* `tags` — List of user-defined tags (set via Edit Tags). Defaults to `[]`.
* Existing sessions without these fields are fully backward-compatible.

## Empty Session Handling

* New sessions no longer create an empty JSON file on startup. The file is only written when the first interaction is appended.
* The session browser automatically excludes sessions with zero interactions.
