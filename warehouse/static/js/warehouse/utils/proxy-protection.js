/* SPDX-License-Identifier: Apache-2.0 */

import docReady from "warehouse/utils/doc-ready";

/**
 * Proxy Protection - Detects if the page is being loaded through a proxy
 * and displays a warning if the domain is not in the allowed list.
 */

function checkProxyProtection() {
  // Get the allowed domains from the data attribute
  const proxyProtectionElement = document.querySelector("[data-allowed-domains]");
  if (!proxyProtectionElement) {
    return;
  }

  const allowedDomainsStr = proxyProtectionElement.dataset.allowedDomains;
  if (!allowedDomainsStr) {
    return;
  }

  // Parse the allowed domains
  let allowedDomains = [];
  try {
    allowedDomains = allowedDomainsStr.split(",");
  } catch (e) {
    console.error("Failed to parse allowed domains:", e);
    return;
  }

  // Get the current domain
  const currentDomain = window.location.hostname;

  // Check if current domain is in the allowed list
  const isAllowed = allowedDomains.some(domain => {
    // Exact match or subdomain match
    return currentDomain === domain || 
           currentDomain.endsWith("." + domain);
  });

  // If domain is allowed, no need to show warning
  if (isAllowed || allowedDomains.length === 0) {
    return;
  }

  // Create and show the phishing warning
  showPhishingWarning();
}

function showPhishingWarning() {
  // Check if warning already exists
  if (document.getElementById("proxy-phishing-warning")) {
    return;
  }

  // Make the entire page red with a warning overlay
  const warningOverlay = document.createElement("div");
  warningOverlay.id = "proxy-phishing-warning";
  warningOverlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(220, 53, 69, 0.95);
    z-index: 99999;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(5px);
  `;

  const warningContent = document.createElement("div");
  warningContent.style.cssText = `
    background-color: white;
    padding: 40px;
    border-radius: 8px;
    max-width: 600px;
    margin: 20px;
    box-shadow: 0 10px 50px rgba(0, 0, 0, 0.5);
    text-align: center;
  `;

  warningContent.innerHTML = `
    <h1 style="color: #dc3545; margin-bottom: 20px; font-size: 28px;">
      <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>
      Security Warning: Potential Phishing Site
    </h1>
    <div style="color: #333; margin-bottom: 30px;">
      <p style="font-size: 18px; margin-bottom: 15px;">
        <strong>Warning:</strong> You are not accessing this site from an official domain.
      </p>
      <p style="margin-bottom: 15px;">
        This could be a phishing attempt. You are currently on:
      </p>
      <p style="font-size: 20px; font-weight: bold; color: #dc3545; margin-bottom: 15px;">
        ${window.location.hostname}
      </p>
      <p style="margin-bottom: 20px;">
        Please verify that you trust this domain before continuing.
      </p>
    </div>
    <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
      <button type="button" 
              id="dismiss-warning-button"
              style="background-color: #6c757d; color: white; border: none; padding: 12px 24px; font-size: 16px; cursor: pointer; border-radius: 4px;">
        Continue Anyway
      </button>
    </div>
  `;

  warningOverlay.appendChild(warningContent);
  document.body.appendChild(warningOverlay);
  
  // Attach click event listener to the dismiss button
  const dismissButton = document.getElementById("dismiss-warning-button");
  if (dismissButton) {
    dismissButton.addEventListener("click", dismissPhishingWarning);
  }

  // Store the original background color before changing it
  document.body.dataset.originalBackgroundColor = document.body.style.backgroundColor || "";
  
  // Change the body background to red for extra emphasis
  document.body.style.backgroundColor = "#dc3545";
}

function dismissPhishingWarning() {
  // Remove the warning overlay
  const warning = document.getElementById("proxy-phishing-warning");
  if (warning) {
    warning.remove();
  }
  
  // Restore the original background color
  const originalBgColor = document.body.dataset.originalBackgroundColor;
  if (originalBgColor !== undefined) {
    document.body.style.backgroundColor = originalBgColor;
    delete document.body.dataset.originalBackgroundColor;
  }
  
  // Add a persistent banner warning
  if (!document.getElementById("proxy-warning-banner")) {
    const banner = document.createElement("div");
    banner.id = "proxy-warning-banner";
    banner.className = "notification-bar notification-bar--danger";
    banner.style.cssText = "position: relative; z-index: 1000;";
    banner.innerHTML = `
      <span class="notification-bar__icon">
        <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>
        <span class="sr-only">Warning:</span>
      </span>
      <span class="notification-bar__message">
        <strong>Security Warning:</strong> You are accessing this site through an untrusted proxy domain (${window.location.hostname}). 
        This may be a phishing attempt.
      </span>
    `;
    document.body.insertBefore(banner, document.body.firstChild);
  }
}

// Initialize proxy protection when DOM is ready
docReady(checkProxyProtection);

export default checkProxyProtection;
