/* SPDX-License-Identifier: Apache-2.0 */

const UNITS = ["B", "KiB", "MiB", "GiB", "TiB"];

/**
 * Render a byte count in binary units, e.g. 1288490188 -> "1.2 GiB".
 *
 * Accepts strings so it can format values read out of table cells. Whole
 * bytes are shown without a decimal, larger units with one.
 */
export default function filesize(bytes) {
  let size = Number(bytes);
  let unit = 0;
  while (size >= 1024 && unit < UNITS.length - 1) {
    size /= 1024;
    unit++;
  }

  return `${unit === 0 ? size : size.toFixed(1)} ${UNITS[unit]}`;
}
