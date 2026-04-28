#!/usr/bin/env node
/* SPDX-License-Identifier: Apache-2.0 */

/* Post-bundler build step:
 *   - Pre-compress text assets (.js, .css, .svg, .html, .map) with gzip and
 *     brotli so whitenoise can serve the .gz/.br sibling without recompressing.
 *   - Image-optimise raster + svg assets in dist/images.
 *
 * Replaces compression-webpack-plugin + image-minimizer-webpack-plugin which
 * were dropped during the rspack swap (no rspack-compatible equivalents).
 *
 * Usage: bun bin/post-build.mjs (or `node bin/post-build.mjs`).
 */

import { readdir, readFile, writeFile, stat } from "node:fs/promises";
import { join, extname } from "node:path";
import { gzip, brotliCompress, constants } from "node:zlib";
import { promisify } from "node:util";

const gzipAsync = promisify(gzip);
const brotliAsync = promisify(brotliCompress);

const DIST_DIRS = ["warehouse/static/dist", "warehouse/admin/static/dist"];

// Files to pre-compress; matches the previous compression-webpack-plugin
// scope (any text-shaped asset where minRatio: 1 made compression worthwhile).
const COMPRESSIBLE = /\.(js|css|svg|html|map|json|txt|wasm)$/i;

// Smaller-after-compression threshold mirrors the old `minRatio: 1`.
const MIN_RATIO = 1;

async function* walk(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch (err) {
    if (err.code === "ENOENT") {
      return;
    }
    throw err;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else if (entry.isFile()) {
      yield full;
    }
  }
}

async function compressOne(file) {
  if (!COMPRESSIBLE.test(file)) {
    return null;
  }
  const buf = await readFile(file);
  const orig = buf.length;
  const [gz, br] = await Promise.all([
    gzipAsync(buf, { level: 9, memLevel: 9 }),
    brotliAsync(buf, {
      params: { [constants.BROTLI_PARAM_QUALITY]: 11 },
    }),
  ]);
  const wrote = [];
  if (gz.length < orig / MIN_RATIO) {
    await writeFile(file + ".gz", gz);
    wrote.push("gz");
  }
  if (br.length < orig / MIN_RATIO) {
    await writeFile(file + ".br", br);
    wrote.push("br");
  }
  return wrote;
}

async function optimiseImages(distDir) {
  const imageDir = join(distDir, "images");
  let imageStat;
  try {
    imageStat = await stat(imageDir);
  } catch (err) {
    if (err.code === "ENOENT") {
      return { raster: 0, svg: 0 };
    }
    throw err;
  }
  if (!imageStat.isDirectory()) {
    return { raster: 0, svg: 0 };
  }

  const sharp = (await import("sharp")).default;
  const { optimize: svgoOptimize } = await import("svgo");

  let raster = 0;
  let svg = 0;
  for await (const file of walk(imageDir)) {
    const ext = extname(file).toLowerCase();
    if (/\.(png|jpe?g|gif)$/.test(ext)) {
      const before = await readFile(file);
      const after = await sharp(before).toBuffer();
      if (after.length < before.length) {
        await writeFile(file, after);
        raster++;
      }
    } else if (ext === ".svg") {
      const before = await readFile(file, "utf8");
      const result = svgoOptimize(before, {
        multipass: true,
        plugins: ["preset-default"],
      });
      if (result.data && result.data.length < before.length) {
        await writeFile(file, result.data);
        svg++;
      }
    }
  }
  return { raster, svg };
}

async function main() {
  const start = Date.now();
  let compressed = 0;
  let imgRaster = 0;
  let imgSvg = 0;

  for (const dir of DIST_DIRS) {
    for await (const file of walk(dir)) {
      // Don't re-compress the compressed siblings or source maps' siblings.
      if (file.endsWith(".gz") || file.endsWith(".br")) {
        continue;
      }
      const wrote = await compressOne(file);
      if (wrote && wrote.length) {
        compressed++;
      }
    }
    const { raster, svg } = await optimiseImages(dir);
    imgRaster += raster;
    imgSvg += svg;
  }

  const ms = Date.now() - start;
  console.log(
    `post-build: pre-compressed ${compressed} files, ` +
      `optimised ${imgRaster} raster + ${imgSvg} svg images in ${ms} ms`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
