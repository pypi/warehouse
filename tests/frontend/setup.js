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

// Extend Jest with jest-dom https://github.com/testing-library/jest-dom
import "@testing-library/jest-dom/extend-expect";

// Required to use async/await in tests
import "@babel/polyfill";

// Monkeypatch the global fetch API
fetch = require("jest-fetch-mock");  // eslint-disable-line no-global-assign

// Make TextEncoder and crypto available in the global scope
// in the same way as in a browser environment
window.TextEncoder = require("util").TextEncoder;
const crypto = require("crypto");
window.crypto = crypto.webcrypto;
