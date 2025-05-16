/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, describe, beforeEach, it */

import timeAgo from "../../warehouse/static/js/warehouse/utils/timeago";
import {delay} from "./utils";

describe("time ago util", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
  });

  it("shows 'just now' for a very recent time'", async () => {
    document.body.innerHTML = `
    <time id="element" datetime="${new Date().toISOString()}"></time>
    `;

    timeAgo();

    await delay(25);

    const element = document.getElementById("element");
    expect(element.innerText).toEqual("Just now");

  });

  it("shows 'About 5 hours ago' for such a time'", async () => {
    const date = new Date();
    date.setHours(date.getHours() - 5);

    document.body.innerHTML = `
    <time id="element" datetime="${date.toISOString()}"></time>
    `;

    timeAgo();

    await delay(25);

    const element = document.getElementById("element");
    expect(element.innerText).toEqual("About 5 hours ago");
  });

  it("shows 'About 36 minutes ago' for such a time'", async () => {
    const date = new Date();
    date.setMinutes(date.getMinutes() - 36);

    document.body.innerHTML = `
    <time id="element" datetime="${date.toISOString()}"></time>
    `;

    timeAgo();

    await delay(25);

    const element = document.getElementById("element");
    expect(element.innerText).toEqual("About 36 minutes ago");
  });

  it("shows provided text for Yesterday'", async () => {
    const date = new Date();
    date.setHours(date.getHours() - 24);

    document.body.innerHTML = `
    <time id="element" datetime="${date.toISOString()}"></time>
    `;

    timeAgo();

    await delay(25);

    const element = document.getElementById("element");
    expect(element.innerText).toEqual("Yesterday");
  });

  it("makes no call when not isBeforeCutoff", async () => {
    document.body.innerHTML = `
    <time id="element" datetime="2019-09-20T19:06:58+0000">existing text</time>
    `;

    timeAgo();

    await delay(25);

    const element = document.getElementById("element");
    expect(element.textContent).toEqual("existing text");
  });
});
