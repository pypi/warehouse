/* SPDX-License-Identifier: Apache-2.0 */

/* global beforeEach, describe, expect, it, jest */

describe("MathJax configuration", () => {
  beforeEach(() => {
    delete window.MathJax;
    jest.resetModules();
  });

  it("loads the ui/safe extension and configures inline math delimiters", async () => {
    await import("../../warehouse/static/js/vendor/mathjax-config.js");

    expect(window.MathJax).toEqual({
      loader: {
        load: ["ui/safe"],
      },
      tex: {
        inlineMath: [["$", "$"], ["\\(", "\\)"]],
      },
    });
  });
});
