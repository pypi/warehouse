/* SPDX-License-Identifier: Apache-2.0 */

/* global beforeAll, describe, expect, it */

import { TextDecoder } from "util";

globalThis.TextDecoder = TextDecoder;

let compileString;

beforeAll(async () => {
  ({ compileString } = await import("sass-embedded"));
});

describe("dark mode styles", () => {
  it("sets the base page colors and links from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/base/typography';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("color-scheme: dark");
    expect(css).toContain("color: #bbb");
    expect(css).toContain("background-color: #000");
    expect(css).toContain("color: rgb(147.5, 215.2312138728, 255)");
  });

  it("dims the footer background from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/footer';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: rgb(0, 76.8670520231, 122)");
  });

  it("dims project cards from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/package-snippet';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: #111");
    expect(css).toContain("border-color: #333");
    expect(css).toContain("color: #bbb");
    expect(css).toContain("background-color: #080808");
    expect(css).toContain("border-color: #888");
    expect(css).toContain("filter: brightness(0.8)");
    expect(css.indexOf("color: #464646")).toBeLessThan(css.indexOf("color: #bbb"));
  });

  it("keeps the admin include readable from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/admin-include';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("#21090d");
    expect(css).toContain("#4a1018");
    expect(css).toContain("color: #fff");
  });

  it("sets search inputs from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/search-form';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: #000");
    expect(css).toContain("border-color: #333");
    expect(css).toContain("color: #bbb");
  });

  it("dims disabled buttons from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/button';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: #1a1a1a");
    expect(css).toContain("border-color: #333");
    expect(css).toContain("color: #bbb");
  });

  it("keeps outline buttons readable from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/button';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("border-color: #888");
    expect(css).toContain("color: #bbb");
    expect(css).toContain("background-color: #111");
  });

  it("sets form fields from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/base/forms';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: #000");
    expect(css).toContain("border-color: #333");
    expect(css).toContain("color: #bbb");
  });

  it("keeps horizontal tabs readable from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/horizontal-tabs';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: #000");
    expect(css).toContain("border-color: #333");
    expect(css).toContain("color: #bbb");
    expect(css).toContain("background-color: #111");
    expect(css).toContain("color: rgb(147.5, 215.2312138728, 255)");
  });

  it("sets the homepage statistics section from the preferred color scheme", () => {
    const { css } = compileString(
      "@use 'warehouse/static/sass/blocks/horizontal-section'; @use 'warehouse/static/sass/blocks/statistics-bar';",
      {
        loadPaths: ["."],
        style: "expanded",
      },
    );

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: #000");
    expect(css).toContain("border-bottom-color: #333");
    expect(css).toContain("border-top-color: #333");
    expect(css).toContain("color: #bbb");
  });

  it("sets the homepage intro text from the preferred color scheme", () => {
    const { css } = compileString(
      "@use 'warehouse/static/sass/blocks/about-pypi'; @use 'warehouse/static/sass/blocks/lede-paragraph';",
      {
        loadPaths: ["."],
        style: "expanded",
      },
    );

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("color: #bbb");
    expect(css.indexOf(".lede-paragraph")).toBeLessThan(css.lastIndexOf("color: #bbb"));
  });

  it("keeps vertical tab hover readable from the preferred color scheme", () => {
    const { css } = compileString("@use 'warehouse/static/sass/blocks/vertical-tabs';", {
      loadPaths: ["."],
      style: "expanded",
    });

    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain("background-color: #111");
    expect(css).toContain("color: rgb(147.5, 215.2312138728, 255)");
  });
});
