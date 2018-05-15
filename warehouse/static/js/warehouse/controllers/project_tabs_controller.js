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
  }

  onTabClick(event) {
    event.preventDefault();
    let btn = event.target;
    this.toggleTab(btn);
  }

  toggleTab(btn) {
    history.pushState(null, "", btn.getAttribute("href"));
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

  _hide(content) {
    content.style.display = "none";
    let tab = this._getTabForContentId(content.getAttribute("id"));
    if (tab) tab.classList.remove(activeClass);
  }

  _show(content) {
    content.style.display = "block";
    let contentId = content.getAttribute("id");
    let tab = this._getTabForContentId(contentId);
    tab.classList.add(activeClass);
    this.data.set("content", contentId);
  }

  _getTabForContentId(contentId) {
    let tabs = this._getTabs();
    return tabs.find(tab => tab.getAttribute("href").substr(1) === contentId);
  }

  _getTabs() {
    return window.innerWidth <= BREAKPOINTS.tablet ?
      this.mobileTabTargets : this.tabTargets;
  }

  _handleResize() {
    if (!this.resizeTimeout) {
      this.resizeTimeout = setTimeout(() => {
        this.resizeTimeout = null;
        let tab = this._getTabForContentId(this.data.get("content"));
        if (!tab) this.toggleTab(this._getTabs()[0]);
      }, 66);
    }
  }

  _handleHashChange() {
    let contentId = window.location.hash.substr(1);
    let tab = this._getTabForContentId(contentId);
    if (tab) this.toggleTab(tab);
  }
}
