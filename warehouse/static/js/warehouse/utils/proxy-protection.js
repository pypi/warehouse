/* SPDX-License-Identifier: Apache-2.0 */

import docReady from "warehouse/utils/doc-ready";

/**
 * Proxy Protection - Detects if the page is being loaded through a proxy
 * and displays a warning if the domain is not in the allowed list.
 */

async function hashDomain(domain, nonce) {
  // Convert strings to ArrayBuffer
  const encoder = new TextEncoder();
  const nonceData = encoder.encode(nonce);
  const domainData = encoder.encode(domain);
  
  // Import the nonce as a key for HMAC
  const key = await crypto.subtle.importKey(
    "raw",
    nonceData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  
  // Generate HMAC
  const signature = await crypto.subtle.sign("HMAC", key, domainData);
  
  // Convert to hex string
  const hashArray = Array.from(new Uint8Array(signature));
  return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

async function checkProxyProtection() {
  // Default to not allowed
  let isAllowed = false;
  
  // Try to get the allowed domains and nonce from data attributes
  const proxyProtectionElement = document.querySelector("[data-allowed-domains][data-request-nonce]");
  
  if (proxyProtectionElement) {
    const hashedDomainsStr = proxyProtectionElement.dataset.allowedDomains;
    const nonce = proxyProtectionElement.dataset.requestNonce;
    
    if (hashedDomainsStr && nonce) {
      // Parse the hashed domains
      let hashedDomains = [];
      try {
        hashedDomains = hashedDomainsStr.split(",").filter(h => h.length > 0);
      } catch (e) {
        console.error("Failed to parse hashed domains:", e);
      }

      if (hashedDomains.length > 0) {
        // Get the current domain
        const currentDomain = window.location.hostname;
        
        // Hash the current domain with the nonce
        const currentDomainHash = await hashDomain(currentDomain, nonce);
        
        // Check if current domain hash is in the allowed list (exact match only)
        isAllowed = hashedDomains.includes(currentDomainHash);
      }
    }
  }

  // Always show warning unless domain explicitly matches
  if (!isAllowed) {
    showPhishingWarning();
  }
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

  // Create header
  const header = document.createElement("h1");
  header.style.cssText = "color: #dc3545; margin-bottom: 20px; font-size: 28px;";
  header.innerHTML = `
    <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>
    Security Warning:<br>Potential Phishing Site
  `;
  warningContent.appendChild(header);

  // Create content div
  const contentDiv = document.createElement("div");
  contentDiv.style.cssText = "color: #333; margin-bottom: 30px;";
  
  const warningP = document.createElement("p");
  warningP.style.cssText = "font-size: 18px; margin-bottom: 15px;";
  warningP.innerHTML = "<strong>Warning:</strong> You are not accessing this site from an official domain.";
  contentDiv.appendChild(warningP);
  
  const messageP = document.createElement("p");
  messageP.style.cssText = "margin-bottom: 15px;";
  messageP.textContent = "This could be a phishing attempt. You are currently on:";
  contentDiv.appendChild(messageP);
  
  // Create hostname display
  const hostnameDiv = document.createElement("div");
  hostnameDiv.style.cssText = "font-size: 72px !important; font-weight: 900 !important; color: #ff6b6b !important; margin: 10px 0; line-height: 1.2; font-family: monospace; word-break: break-all;";
  hostnameDiv.textContent = window.location.hostname;
  contentDiv.appendChild(hostnameDiv);
  
  const verifyP = document.createElement("p");
  verifyP.style.cssText = "margin-bottom: 20px;";
  verifyP.textContent = "Please verify that you trust this domain before continuing.";
  contentDiv.appendChild(verifyP);
  
  warningContent.appendChild(contentDiv);
  
  // Create button container
  const buttonDiv = document.createElement("div");
  buttonDiv.style.cssText = "display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;";
  
  const dismissButton = document.createElement("button");
  dismissButton.type = "button";
  dismissButton.id = "dismiss-warning-button";
  dismissButton.style.cssText = "background-color: #6c757d; color: white; border: none; padding: 12px 24px; font-size: 16px; cursor: pointer; border-radius: 4px;";
  dismissButton.textContent = "Continue Anyway";
  
  buttonDiv.appendChild(dismissButton);
  warningContent.appendChild(buttonDiv);

  warningOverlay.appendChild(warningContent);
  document.body.appendChild(warningOverlay);
  
  // Attach click event listener to the dismiss button
  dismissButton.addEventListener("click", dismissPhishingWarning);

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
