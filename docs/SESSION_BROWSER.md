# Sessions — Saving, Structure & Browsing

This document explains how SnapSolve captures, persists, and organizes session data, and how to browse it.

## When Sessions Are Saved

Session data is persisted at several points during the application lifecycle:

### 1. LLM Response Received (Primary Save Point)

Every successful LLM interaction triggers a full save via `append_interaction()`. This is the main
save point and captures the complete interaction:

```
User action → Source extracts data → Pipeline builds prompt → LLM responds → Session saved
```

This covers:
- **Text prompts** submitted via the control panel → sent to LLM → response saved
- **Screenshot/OCR captures** → text extracted → sent to LLM → response saved (image is also copied
  to the session's `images/` folder if `save_images` is enabled)
- **Audio recordings** → transcribed to text → sent to LLM → response saved

The save is performed in `process_pipeline()` (`core/pipeline/pipeline.py`) after the LLM finishes,
for **both** the single-model path and the fallback-concurrency path. Only interactions with a
non-error response are persisted — if the LLM returns an error (after all retries), the interaction
is not saved.

**What is stored per interaction:**

| Field            | Description                                                    |
|------------------|----------------------------------------------------------------|
| `timestamp`      | Unix timestamp of when the interaction was saved               |
| `prompt`         | The full prompt text sent to the LLM                           |
| `response`       | The full LLM response text                                     |
| `extracted_text`  | Raw text extracted by OCR (if applicable)                      |
| `source`         | Source type: `"text"`, `"image"`, or `"audio"`                 |
| `speaker_name`   | The configured speaker name (e.g., `"interviewer"`)            |
| `image`          | Relative path to the captured image (e.g., `images/interaction_0.png`) |

### 2. Real-Time Transcription Segments

During audio recording with WhisperLive real-time transcription enabled, each completed utterance
is appended to the session's `transcription.txt` file as it happens — **before** the recording
is stopped or sent to the LLM. This is handled by `append_transcription_segment()` in the
`SessionManager`.

Each line is prefixed with the speaker name:

```
[interviewer] Hello, can you explain this concept?
[interviewer] I mean the part about neural networks.

--- AI Response (2026-05-29 14:30:00) ---
Neural networks are computational models inspired by...

--- [interviewer] ---
[interviewer] What about backpropagation?
```

### 3. New Session Created

When a new session starts (via hotkey or on app launch), the session folder is created immediately
with the directory structure in place. The `session.json` file itself is written on the first
interaction.

### 4. Session Metadata Updates

The session JSON is also re-saved when:
- A session is **renamed** (via the Session Browser context menu)
- **Tags** are added or modified (via the Session Browser context menu)

## Per-Session Folder Structure

Each session is stored in its own folder under `sessions/`:

```
sessions/
├── <session-uuid>/
│   ├── session.json          # Session metadata + interaction history
│   ├── images/               # Captured images (OCR screenshots)
│   │   ├── interaction_0.png
│   │   └── interaction_1.png
│   └── transcription.txt     # Speaker-attributed transcription log
├── <another-session-uuid>/
│   └── ...
```

### session.json Format

```json
{
    "id": "508f94f4-66df-4527-a195-4ae942a3e431",
    "title": "auto-generated from first prompt (50 chars)",
    "name": "user-defined name or null",
    "tags": ["interview", "python"],
    "speaker_name": "interviewer",
    "updated_at": 1234567890.123,
    "history": [
        {
            "timestamp": 1234567890.123,
            "prompt": "explain the difference between lists and tuples",
            "response": "Lists are mutable sequences...",
            "extracted_text": null,
            "source": "text",
            "speaker_name": "interviewer",
            "image": "images/interaction_0.png"
        }
    ]
}
```

| Top-Level Field  | Description                                              |
|-------------------|----------------------------------------------------------|
| `id`              | UUID of the session                                      |
| `title`           | Auto-generated from the first 50 chars of the first prompt |
| `name`            | User-defined name (set via Rename in Session Browser)    |
| `tags`            | User-defined tags for filtering                          |
| `speaker_name`    | Default speaker name for this session                    |
| `updated_at`      | Unix timestamp of the last save                          |
| `history`         | Array of interaction objects                              |

### Legacy Session Migration

Sessions created before the folder structure was introduced (stored as flat `sessions/<uuid>.json`
files) are **transparently migrated** on first access. The migration:

1. Creates the `sessions/<uuid>/` folder with `images/` subfolder
2. Moves the JSON into `sessions/<uuid>/session.json`
3. Relocates any referenced images from the shared `sessions/images/` folder
4. Removes the original flat file

You can also run the migration manually:

```bash
python scripts/migrate_sessions.py
```

## Configuration

Session behavior is controlled by these settings (configurable via Settings UI or `config.json`):

| Setting              | Default         | Description                                         |
|----------------------|-----------------|-----------------------------------------------------|
| `save_images`        | `true`          | Copy captured images into the session's images folder |
| `save_transcriptions`| `true`          | Write transcription segments to `transcription.txt` |
| `speaker_name`       | `"interviewer"` | Name attributed to the speaker in transcription files |

## Session Lifecycle

```
App starts
  │
  ├─ If --continue-last or --continue-session → load existing session
  │   └─ Session folder is verified/created if missing
  │
  └─ Otherwise → start_new_session()
      └─ Creates sessions/<uuid>/ with images/ subfolder
         └─ Sets transcription_file = sessions/<uuid>/transcription.txt

User interacts
  │
  ├─ Text prompt → TextSource → LLM → append_interaction() → session.json updated
  │
  ├─ Screenshot capture → ScreenshotSource (OCR) → LLM → append_interaction()
  │   └─ Image copied to sessions/<uuid>/images/interaction_N.png
  │
  ├─ Audio recording → SoundSource
  │   ├─ Real-time: each utterance → append_transcription_segment() → transcription.txt
  │   └─ On stop (long press): transcribed text → LLM → append_interaction()
  │
  └─ New Chat Session hotkey → start_new_session() → new folder created

Session Browser (Ctrl+Alt+Shift+B)
  └─ Scans sessions/**/session.json → displays tree → user can browse/rename/tag/delete
```

## Session Browser

### Opening

- **Hotkey:** Press `Ctrl + Alt + Shift + B` (configurable in Settings → Keyboard Shortcuts)
- **Control Panel:** Click the **📋 Sessions** button

### Interface Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🔍 Filter by tag or session name…                                   │
├────────────────────────┬─────────────────────────────────────────────┤
│                        │  📝 Prompt                                  │
│  Session Tree          │  [interviewer]  (audio)  📎 images/int_0.png│
│  (left panel)          │  ──────────────────────────────────────────  │
│                        │  explain the difference between...          │
│  📁 2026-05-29 — Name  │  ─────────────────── (adjustable splitter)  │
│    💬 text prompt...   │  💬 Response                                │
│    🎤 audio prompt...  │  (rendered Markdown with syntax highlight)  │
│    🖼️ image prompt...  │                                             │
├────────────────────────┴─────────────────────────────────────────────┤
│ Status: 42 sessions • 187 prompts                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### Session Tree (Left Panel)

- Sessions are root items sorted by date (most recent first)
- Each shows: `📁 YYYY-MM-DD HH:MM — Session Name [tag1] [tag2]`
- Child items show prompt excerpts with **source-type icons**:
  - 💬 Text prompts
  - 🎤 Audio prompts
  - 🖼️ Image/OCR prompts
- The latest session is expanded by default
- Empty sessions (no interactions) are automatically hidden
- **Multi-select** supported: `Ctrl+Click` or `Shift+Click`

### Content Viewer (Right Panel)

When a prompt is selected:

- **Top: Prompt panel** — Shows the speaker name, source type, attached image path (if any),
  and the full prompt text
- **Bottom: Response panel** — Renders the formatted response using Markdown, LaTeX/KaTeX,
  Shiki syntax highlighting, and Mermaid diagrams

### Session Management

| Action           | How                                              |
|------------------|--------------------------------------------------|
| Rename           | Right-click → ✏️ Rename Session                  |
| Edit Tags        | Right-click → 🏷️ Edit Tags (comma-separated)    |
| Delete           | Right-click → 🗑️ Delete, or press `Delete` key   |
| Multi-delete     | Select multiple → right-click → Delete N Sessions |
| Filter           | Type in the 🔍 filter bar (matches name/title/tags) |

### Empty Session Handling

- New sessions create the folder immediately but only write `session.json` on the first interaction
- The Session Browser automatically excludes sessions with zero interactions
