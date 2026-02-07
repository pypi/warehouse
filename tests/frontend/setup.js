/* SPDX-License-Identifier: Apache-2.0 */

// Extend Jest with jest-dom https://github.com/testing-library/jest-dom
import "@testing-library/jest-dom";

// Monkeypatch the global fetch API
import fetchMock from "jest-fetch-mock";
fetchMock.enableMocks();

// Make TextEncoder and crypto available in the global scope
// in the same way as in a browser environment
window.TextEncoder = require("util").TextEncoder;
const crypto = require("crypto");
window.crypto.subtle = crypto.webcrypto.subtle;
