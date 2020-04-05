/* Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* global fetch */

// Setup MutationObserver shim since jsdom doesn't
// support it out of the box.

const fs = require("fs");
const path = require("path");

const shim = fs.readFileSync(
  path.resolve(
    "node_modules",
    "mutationobserver-shim",
    "dist",
    "mutationobserver.min.js"
  ),
  { encoding: "utf-8" }
);
const script = window.document.createElement("script");
script.textContent = shim;

window.document.body.appendChild(script);

// Extend Jest with jest-dom https://github.com/testing-library/jest-dom
import "@testing-library/jest-dom/extend-expect";

// Required to use async/await in tests
import "@babel/polyfill";

// Monkeypatch the global fetch API
fetch = require("jest-fetch-mock");  // eslint-disable-line no-global-assign no-redeclare no-unused-vars

// Make TextEncoder and cryto available in the global scope
// in the same way as in a browser environment
window.TextEncoder = require("util").TextEncoder;
const WebCrypto = require("node-webcrypto-ossl");
window.crypto = new WebCrypto();
