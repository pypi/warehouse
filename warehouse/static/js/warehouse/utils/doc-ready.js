/* SPDX-License-Identifier: Apache-2.0 */

export default (fn) => {
  if (document.readyState != "loading") { fn(); }
  else { document.addEventListener("DOMContentLoaded", fn); }
};
