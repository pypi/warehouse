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
// These values should be kept in sync with the CSS breakpoints
const BREAKPOINTS = {
  "mobile": 400,
  "small-tablet": 600,
  "tablet": 800,
  "desktop": 1000,
  "large-desktop": 1200,
};

export default class extends Controller {
  static targets = ["switchToDesktop", "switchToMobile"];

  connect() {
    // Set initial breakpoint value
    this._setBreakpointValue(window.innerWidth);
    // Handle resizing events to update the value
    window.addEventListener("resize", this._handleResize, false);
    this.resizeTimeout = null;
    // Check if localStorage has already been set
    const showDesktop = localStorage.getItem("showDesktop");
    if (showDesktop) {
      // Already been switched to desktop before, so show the mobile button
      this.switchToMobileTarget.classList.remove("hidden");
      // And resize again
      this._setViewport(DESKTOP_WIDTH);
    } else {
      // If we get here, JS is enabled, so show the "Switch To Desktop" button
      this.switchToDesktopTarget.classList.remove("hidden");
    }
  }

  _handleResize() {
    if (!this.resizeTimeout) {
      let resizeTimeout = this.resizeTimeout;
      let _setBreakpointValue = this._setBreakpointValue;
      this.resizeTimeout = setTimeout(function () {
        resizeTimeout = null;
        _setBreakpointValue(window.innerWidth);
      }, 66);
    }
  }

  _setBreakpointValue(width) {
    let currentBreakpoint = BREAKPOINTS.mobile;
    for (let breakpoint in BREAKPOINTS) {
      console.log(breakpoint);
      if (width > BREAKPOINTS[breakpoint]) {
        currentBreakpoint = breakpoint;
      } else {
        break;
      }
    }
    this.data.set("breakpoint", currentBreakpoint);
  }

  _setViewport(width) {
    const content = `width=${width}`;
    document.getElementsByTagName("meta")["viewport"].content = content;
    window.scrollTo(0, 0);
  }

  switchToDesktop() { // Toggle to the desktop viewport.
    // Store the original width to reuse on the next page load to resize again.
    this.switchToMobileTarget.classList.remove("hidden");
    this.switchToDesktopTarget.classList.add("hidden");
    localStorage.setItem("showDesktop", 1);
    this._setViewport(DESKTOP_WIDTH);
  }

  switchToMobile() { // Reset to the original viewport
    this.switchToMobileTarget.classList.add("hidden");
    this.switchToDesktopTarget.classList.remove("hidden");
    localStorage.removeItem("showDesktop");
    this._setViewport("device-width");
  }
}
