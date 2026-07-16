/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

const activeClass = "project-tabs__tab--is-active";

export default class extends Controller {
  static targets = ["tab", "content"];

  connect() {
    const contentId = window.location.hash.slice(1);
    this.toggleTab(this._getTabForContentId(contentId) || this.tabTargets[0]);
    this._handleHashChange = this._handleHashChange.bind(this);
    window.addEventListener("hashchange", this._handleHashChange, false);
  }

  disconnect() {
    window.removeEventListener("hashchange", this._handleHashChange);
  }

  tabClick(event) {
    event.preventDefault();
    const btn = event.currentTarget;
    this.toggleTab(btn);
    history.pushState(null, "", btn.hash);
    document.getElementById(btn.hash.slice(1))?.focus({ preventScroll: true });
  }

  toggleTab(btn) {
    if (!btn || !btn.hash) return;
    const contentId = btn.hash.slice(1);

    // If btn lives inside a content panel it's an inline sub-panel link (e.g. "view details").
    // In that case keep the parent content panel's nav tab active instead.
    const parentContent = this.contentTargets.find(c => c.contains(btn));
    const activeNavTab = parentContent
      ? this._getNavTabForContentId(parentContent.id)
      : this._getNavTabForContentId(contentId);

    this.contentTargets.forEach(content => {
      content.style.display = content.id === contentId ? "block" : "none";
    });

    this.tabTargets
      .filter(tab => !this.contentTargets.some(c => c.contains(tab)))
      .forEach(tab => {
        const isActive = tab === activeNavTab;
        tab.classList.toggle(activeClass, isActive);
        if (isActive) {
          tab.setAttribute("aria-selected", "true");
        } else {
          tab.removeAttribute("aria-selected");
        }
      });
  }

  _getTabForContentId(contentId) {
    return this.tabTargets.find(tab => tab.hash.slice(1) === contentId);
  }

  _getNavTabForContentId(contentId) {
    return this.tabTargets.find(tab =>
      tab.hash.slice(1) === contentId &&
      !this.contentTargets.some(c => c.contains(tab)),
    );
  }

  _handleHashChange() {
    const contentId = window.location.hash.slice(1);
    if (!contentId) {
      this.toggleTab(this.tabTargets[0]);
    } else {
      const tab = this._getTabForContentId(contentId);
      if (tab) {
        this.toggleTab(tab);
      }
    }
  }
}
