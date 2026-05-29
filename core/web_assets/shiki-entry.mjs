/**
 * Shiki IIFE bundle entry point.
 *
 * Bundled by esbuild into a single file that can be loaded via a regular
 * <script> tag inside QWebEngineView (no ES module support needed).
 *
 * Exposes:
 *   window.shikiReady    — Promise that resolves when the highlighter is ready
 *   window.shikiHighlight(code, lang) — returns highlighted HTML string (sync after init)
 */

import { createHighlighterCore } from 'shiki/core';
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript';

// Theme
import ayuDark from '@shikijs/themes/ayu-dark';

// Languages — curated set of common languages an LLM might generate
import python from '@shikijs/langs/python';
import javascript from '@shikijs/langs/javascript';
import typescript from '@shikijs/langs/typescript';
import html from '@shikijs/langs/html';
import css from '@shikijs/langs/css';
import json from '@shikijs/langs/json';
import bash from '@shikijs/langs/bash';
import shellscript from '@shikijs/langs/shellscript';
import sql from '@shikijs/langs/sql';
import java from '@shikijs/langs/java';
import c from '@shikijs/langs/c';
import cpp from '@shikijs/langs/cpp';
import csharp from '@shikijs/langs/csharp';
import go from '@shikijs/langs/go';
import rust from '@shikijs/langs/rust';
import ruby from '@shikijs/langs/ruby';
import php from '@shikijs/langs/php';
import yaml from '@shikijs/langs/yaml';
import xml from '@shikijs/langs/xml';
import markdown from '@shikijs/langs/markdown';
import diff from '@shikijs/langs/diff';
import dockerfile from '@shikijs/langs/dockerfile';
import kotlin from '@shikijs/langs/kotlin';
import swift from '@shikijs/langs/swift';
import lua from '@shikijs/langs/lua';
import powershell from '@shikijs/langs/powershell';
import toml from '@shikijs/langs/toml';
import ini from '@shikijs/langs/ini';
import latex from '@shikijs/langs/latex';
import r from '@shikijs/langs/r';
import scala from '@shikijs/langs/scala';
import haskell from '@shikijs/langs/haskell';

let highlighter = null;

// Set of loaded language IDs for fast lookup
let loadedLangs = new Set();

window.shikiReady = (async () => {
    const langs = [
        python, javascript, typescript, html, css, json,
        bash, shellscript, sql, java, c, cpp, csharp,
        go, rust, ruby, php, yaml, xml, markdown, diff,
        dockerfile, kotlin, swift, lua, powershell, toml,
        ini, latex, r, scala, haskell,
    ];

    highlighter = await createHighlighterCore({
        themes: [ayuDark],
        langs: langs,
        engine: createJavaScriptRegexEngine(),
    });

    // Build the set of loaded language IDs (including aliases)
    for (const lang of highlighter.getLoadedLanguages()) {
        loadedLangs.add(lang);
    }
})();

/**
 * Highlight a code string. Returns an HTML string with inline styles.
 * If the highlighter isn't ready or the language is unknown, returns null
 * so the caller can fall back to plain text.
 */
window.shikiHighlight = function (code, lang) {
    if (!highlighter) return null;

    // Normalise language identifier
    lang = (lang || '').toLowerCase().trim();
    if (!lang || !loadedLangs.has(lang)) return null;

    try {
        return highlighter.codeToHtml(code, {
            lang: lang,
            theme: 'ayu-dark',
        });
    } catch (e) {
        console.warn('[shiki] highlight error:', e);
        return null;
    }
};
