/* SPDX-License-Identifier: Apache-2.0 */

/*

Mock debounce module. Jest will import this file automatically
on all test suites that import debounce. For more information see:
https://jestjs.io/docs/en/manual-mocks

*/

/* global jest, module */

const debounce = jest.createMockFromModule("debounce");

function mockDebounce(fn) {
  // Return the wrapped function unchanged.
  return fn;
}

debounce.debounce = mockDebounce;
module.exports = debounce;
