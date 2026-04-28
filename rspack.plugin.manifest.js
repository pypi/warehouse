/* SPDX-License-Identifier: Apache-2.0 */

/* Tiny rspack-compatible manifest plugin.
 *
 * Emits a JSON file that maps logical (un-hashed) asset names to their actual
 * (content-hashed) on-disk paths. Replaces webpack-manifest-plugin and
 * rspack-manifest-plugin, both of which hook `beforeRun` in a way rspack does
 * not implement.
 *
 * Supports the four options warehouse uses:
 *   - filename       Output JSON filename (default: "manifest.json")
 *   - publicPath     Prepended to every value (default: "")
 *   - removeKeyHash  RegExp; matched portions are stripped from KEYS (the
 *                    "logical" name); values keep the hash so the served URL
 *                    actually refers to the cache-busted file.
 *   - seed           Object merged into the output map (used to share state
 *                    across multiple compilations, mirroring the upstream
 *                    plugin's seed semantics).
 *   - map            (file: {name, path}) => {name, path}; lets warehouse
 *                    rewrite keys/values (e.g. add the `js/` or `css/`
 *                    directory prefix). Mutating the input is fine.
 */

/* global module */

const PLUGIN_NAME = "WarehouseManifestPlugin";

class ManifestPlugin {
  constructor(options = {}) {
    this.filename = options.filename || "manifest.json";
    this.publicPath = options.publicPath || "";
    this.removeKeyHash = options.removeKeyHash;
    this.seed = options.seed;
    this.map = options.map || ((file) => file);
  }

  apply(compiler) {
    const {sources, Compilation} = compiler.webpack;

    compiler.hooks.thisCompilation.tap(PLUGIN_NAME, (compilation) => {
      compilation.hooks.processAssets.tap(
        {
          name: PLUGIN_NAME,
          stage: Compilation.PROCESS_ASSETS_STAGE_REPORT,
        },
        () => {
          const manifest = this.seed || {};
          const stats = compilation.getStats().toJson({
            assets: true,
            chunks: false,
            modules: false,
            hash: false,
            version: false,
            timings: false,
            builtAt: false,
          });

          for (const asset of stats.assets) {
            // Skip source maps and pre-compressed siblings — they shouldn't
            // appear in the manifest as primary assets.
            if (/\.(map|gz|br)$/.test(asset.name)) {continue;}

            let key = asset.name;
            if (this.removeKeyHash) {
              key = key.replace(this.removeKeyHash, "");
            }
            const file = this.map({name: key, path: asset.name});
            manifest[file.name] = this.publicPath + file.path;
          }

          const json = JSON.stringify(manifest, null, 2);
          compilation.emitAsset(this.filename, new sources.RawSource(json));
        },
      );
    });
  }
}

module.exports = ManifestPlugin;
