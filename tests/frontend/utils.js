/* SPDX-License-Identifier: Apache-2.0 */

export function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms || 0));
}
