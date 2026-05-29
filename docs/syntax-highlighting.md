# Syntax Highlighting with Shiki

SnapSolve uses [Shiki](https://shiki.style/) to provide highly accurate, VS Code-quality syntax highlighting for code blocks inside the application's Markdown popups.

## Why Shiki?

Unlike traditional regular-expression-based highlighters (like highlight.js or Prism.js), Shiki uses the exact same **TextMate grammars** as Visual Studio Code. This ensures complex languages (like Python, TypeScript, and Rust) are tokenized with maximum precision. Furthermore, Shiki bakes the colors directly into the HTML (`style="..."` attributes) avoiding the need for external CSS theme stylesheets.

## Architecture & Bundling

Because SnapSolve renders its UI inside a Qt `QWebEngineView`, loading external ES Modules or WASM binaries from CDNs poses security and latency challenges (due to the `file://` or opaque origin contexts).

To solve this, we pre-compile Shiki into a single **Immediately Invoked Function Expression (IIFE)** bundle.

*   **No Setup Required:** The bundled file (`core/web_assets/shiki.bundle.js`) is checked into the Git repository. When you move the project to a new computer, you **do not** need to install Node.js or run any build commands for syntax highlighting to work out of the box.
*   **WASM-Free:** The bundle uses Shiki's pure JavaScript RegExp engine instead of the default Onigasm/WASM engine. This ensures flawless execution inside the Qt WebEngine without running into WebAssembly compilation limitations.
*   **Size:** The bundle is approximately 2.5MB and is loaded locally from disk.

## Supported Languages

The bundle currently includes the `ayu-dark` theme and **32 pre-configured languages**, covering the vast majority of AI-generated code:

`python, javascript, typescript, html, css, json, bash, shellscript, sql, java, c, cpp, csharp, go, rust, ruby, php, yaml, xml, markdown, diff, dockerfile, kotlin, swift, lua, powershell, toml, ini, latex, r, scala, haskell`

If an unknown language is encountered, it gracefully falls back to a plain, unstyled code block.

---

## Modifying or Rebuilding the Bundle

If you want to change the theme, add a new programming language, or update Shiki to a newer version, you must rebuild the bundle using Node.js.

### Prerequisites

You must have [Node.js](https://nodejs.org/) installed on your machine.

### Build Instructions

1. Open a terminal and navigate to the web assets directory:
   ```bash
   cd core/web_assets
   ```

2. Install the necessary build dependencies (`shiki` and `esbuild`):
   ```bash
   npm install
   ```

3. Modify the entry point script (`shiki-entry.mjs`) to add your desired languages or change the theme.

4. Run the build script to regenerate the bundle:
   ```bash
   node build-shiki.mjs
   ```

5. The script will automatically overwrite `shiki.bundle.js` with the newly compiled version.

---

## Testing Syntax Highlighting

To verify that the highlighting, LaTeX math, and Mermaid diagrams are rendering correctly, there are two easy testing procedures provided.

### 1. Standalone Browser Test

You can test the frontend rendering logic completely independently of the Python/Qt backend. 
`test-shiki.html` is a comprehensive test page designed for this purpose.

1. Start a local HTTP server in the assets directory:
   ```bash
   cd core/web_assets
   python -m http.server 8765
   ```
2. Open your web browser and navigate to: [http://localhost:8765/test-shiki.html](http://localhost:8765/test-shiki.html)

### 2. Native Qt App Test (Open URL)

To ensure that the `QWebEngineView` (the embedded browser inside SnapSolve) behaves identically to your standard browser, you can load the test page directly into the app using a hidden diagnostic hotkey.

1. Start the HTTP server as shown above.
2. Launch SnapSolve (`python main.py`).
3. Press the Open URL hotkey: **`Ctrl + Alt + U`**.
4. A small text input popup will appear.
5. Type `http://localhost:8765/test-shiki.html` and press **Enter**.
6. The main floating popup will appear and load the test page using the exact Chromium engine used by SnapSolve, confirming everything works inside the native environment.
