/**
 * Build script — produces shiki.bundle.js (IIFE format) from shiki-entry.mjs.
 *
 * Usage:
 *   cd core/web_assets
 *   npm install shiki @shikijs/themes @shikijs/langs esbuild
 *   node build-shiki.mjs
 */

import * as esbuild from 'esbuild';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { readFileSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const result = await esbuild.build({
    entryPoints: [join(__dirname, 'shiki-entry.mjs')],
    bundle: true,
    minify: true,
    format: 'iife',
    outfile: join(__dirname, 'shiki.bundle.js'),
    target: 'es2022',
    platform: 'browser',
    metafile: true,
});

// Report bundle size
const outBytes = Object.values(result.metafile.outputs)[0].bytes;
const outKB = (outBytes / 1024).toFixed(1);
console.log(`✓ Built shiki.bundle.js — ${outKB} KB`);
