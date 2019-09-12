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

// These values should be kept in sync with the CSS breakpoints
const BREAKPOINTS = {
  "mobile": 400,
  "small-tablet": 600,
  "tablet": 800,
  "desktop": 1000,
  "large-desktop": 1200,
};

const activeClass = "vertical-tabs__tab--is-active";

export default class extends Controller {
  static targets = ["tab", "mobileTab", "content"];

  connect() {
    // Set up initial content
    let contentId = window.location.hash.substr(1);
    this.toggleTab(this._getTabForContentId(contentId) || this._getTabs()[0]);
    // Handle resizing events to update the displayed content
    this.resizeTimeout = null;
    this._handleResize = this._handleResize.bind(this);
    window.addEventListener("resize", this._handleResize, false);
    // Handle hash change events to update the displayed content
    this._handleHashChange = this._handleHashChange.bind(this);
    window.addEventListener("hashchange", this._handleHashChange, false);
    // force scrolling after hiding element, only necessary in Firefox
    if (contentId) {
      window.location.hash = "#" + contentId;
    }
  }

  onTabClick(event) {
    event.preventDefault();
    let btn = event.target;
    this.toggleTabAndPushState(btn);

    // Focus tab, only on click
    let contentId = window.location.hash.substr(1);
    document.getElementById(contentId).focus();
  }

  toggleTab(btn) {
    let contentId = btn.getAttribute("href").substr(1);
    // toggle display setting for the content related to the tab button
    this.contentTargets.forEach(content => {
      if (content.getAttribute("id") !== contentId) {
        this._hide(content);
      } else {
        this._show(content);
      }
    });
  }

  toggleTabAndPushState(btn) {
    this.toggleTab(btn);
    history.pushState(null, "", btn.getAttribute("href"));
  }

  _hide(content) {
    content.style.display = "none";
    let contentId = content.getAttribute("id");
    this._getAllTabsForContentId(contentId)
      .forEach(tab => {
        tab.classList.remove(activeClass);
        tab.removeAttribute("aria-selected");
      });
  }

  _show(content) {
    content.style.display = "block";
    let contentId = content.getAttribute("id");
    this._getAllTabsForContentId(contentId)
      .forEach(tab => {
        tab.classList.add(activeClass);
        tab.setAttribute("aria-selected", "true");
      });
    this.data.set("content", contentId);
  }

  _getTabForContentId(contentId) {
    let tabs = this._getTabs();
    return tabs.find(tab => tab.getAttribute("href").substr(1) === contentId);
  }

  _getAllTabsForContentId(contentId) {
    return Array.of(...this.tabTargets, ...this.mobileTabTargets)
      .filter(tab => tab.getAttribute("href").substr(1) === contentId);
  }

  _getTabs() {
    return window.innerWidth <= BREAKPOINTS.tablet ?
      this.mobileTabTargets : this.tabTargets;
  }

  _handleResize() {
    // throttle resize event to 15fps
    if (!this.resizeTimeout) {
      this.resizeTimeout = setTimeout(() => {
        this.resizeTimeout = null;
        let tab = this._getTabForContentId(this.data.get("content"));
        if (!tab) {
          let btn = this._getTabs()[0];
          this.toggleTabAndPushState(btn);
        }
      }, 66);
    }
  }

  _handleHashChange() {
    let contentId = window.location.hash.substr(1);
    if (!contentId) {
      this.toggleTab(this._getTabs()[0]);
    } else {
      let tab = this._getTabForContentId(contentId);
      if (tab) {
        this.toggleTabAndPushState(tab);
      }
    }
  }
}
