/**
 * Licensed under the Apache License, Version 2.0 (the "License");
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

import { Controller } from "stimulus";

// A constant value with represents a usual desktop viewport width
const DESKTOP_WIDTH = 1280;

export default class extends Controller {
  static targets = ["switchToDesktop", "switchToMobile"];

  connect() {
    // Check if localStorage has already been set
    const originalWidth = localStorage.getItem("originalWidth");
    if (originalWidth) {
      // Already been switched to desktop before, so show the mobile button
      this.switchToMobileTarget.classList.remove("hidden");
      // And resize again
      this._setViewport(DESKTOP_WIDTH, originalWidth/DESKTOP_WIDTH);
    } else {
      // If we get here, JS is enabled, so show the "Switch To Desktop" button
      this.switchToDesktopTarget.classList.remove("hidden");
    }
  }

  _setViewport(width, initialScale) {
    document.getElementsByTagName("meta")["viewport"].content = (
      `width=${width}, initial-scale=${initialScale}`
    );
  }

  switchToDesktop() { // Toggle to the desktop viewport.
    // Store the original width to reuse on the next page load to resize again.
    this.switchToMobileTarget.classList.remove("hidden");
    localStorage.setItem("originalWidth", window.innerWidth);
    this._setViewport(DESKTOP_WIDTH, window.innerWidth/DESKTOP_WIDTH);
  }

  switchToMobile() { // Reset to the original viewport
    this.switchToMobileTarget.classList.add("hidden");
    localStorage.removeItem("originalWidth");
    this._setViewport("device-width", 1);
  }
}
