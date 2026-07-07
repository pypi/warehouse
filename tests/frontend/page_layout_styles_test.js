/* SPDX-License-Identifier: Apache-2.0 */

/* global describe, expect, it */

import path from "node:path";
import {cwd} from "node:process";
import {TextDecoder} from "node:util";


describe("base layout styles", () => {
  it("keeps the footer below short page content", async () => {
    // sass-embedded expects TextDecoder on globalThis, while Jest runs in jsdom.
    globalThis.TextDecoder = TextDecoder;

    const sass = await import("sass-embedded");
    const {css} = sass.compile(
      path.join(cwd(), "warehouse/static/sass/base/_typography.scss"),
    );

    expect(css).toContain("body {");
    expect(css).toContain("display: flex;");
    expect(css).toContain("flex-direction: column;");
    expect(css).toContain("min-height: 100vh;");
    expect(css).toContain("main {");
    expect(css).toContain("flex: 1 0 auto;");
  });
});
