/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

const activeClass = "project-tabs__tab--is-active";

export default class extends Controller {
  static targets = ["tab", "content"];

  connect() {
    let contentId = window.location.hash.slice(1);
    this.toggleTab(this._getTabForContentId(contentId) || this.tabTargets[0]);
    this._handleHashChange = this._handleHashChange.bind(this);
    window.addEventListener("hashchange", this._handleHashChange, false);
    // Force scroll after hiding element — Firefox fix
    if (contentId) {
      window.location.hash = "#" + contentId;
    }
  }

  disconnect() {
    window.removeEventListener("hashchange", this._handleHashChange);
  }

  onTabClick(event) {
    event.preventDefault();
    let btn = event.currentTarget;
    this.toggleTabAndPushState(btn);
    let contentId = window.location.hash.slice(1);
    document.getElementById(contentId).focus();
  }

  toggleTab(btn) {
    let contentId = btn.hash.slice(1);
    this.contentTargets.forEach(content => {
      if (content.id !== contentId) {
        this._hide(content);
      } else {
        this._show(content);
      }
    });
  }

  toggleTabAndPushState(btn) {
    this.toggleTab(btn);
    history.pushState(null, "", btn.hash);
  }

  _hide(content) {
    content.style.display = "none";
    const tab = this._getTabForContentId(content.id);
    if (tab) {
      tab.classList.remove(activeClass);
      tab.removeAttribute("aria-selected");
    }
  }

  _show(content) {
    content.style.display = "block";
    const tab = this._getTabForContentId(content.id);
    if (tab) {
      tab.classList.add(activeClass);
      tab.setAttribute("aria-selected", "true");
    }
    this.data.set("content", content.id);
  }

  _getTabForContentId(contentId) {
    return this.tabTargets.find(tab => tab.hash.slice(1) === contentId);
  }

  _handleHashChange() {
    let contentId = window.location.hash.slice(1);
    if (!contentId) {
      this.toggleTab(this.tabTargets[0]);
    } else {
      let tab = this._getTabForContentId(contentId);
      if (tab) {
        this.toggleTabAndPushState(tab);
      }
    }
  }
}
