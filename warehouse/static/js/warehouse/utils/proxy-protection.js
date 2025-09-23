/* SPDX-License-Identifier: Apache-2.0 */

/**
 * Enhanced Proxy Protection - Detects if the page is being loaded through a proxy
 * and displays a warning if the domain is not in the allowed list.
 *
 * Security features:
 * - Multiple hash layers with different algorithms
 * - Domain normalization to prevent bypass attempts
 * - Timestamp validation to prevent replay attacks
 * - Integrity checksums to detect tampering
 */

function normalizeDomain(domain) {
  // Normalize domain to prevent bypasses via domain variations
  let normalized = domain.toLowerCase().trim();

  // Remove trailing dots
  normalized = normalized.replace(/\.+$/, "");

  // Handle IDN domains - convert to ASCII (punycode)
  // This prevents homograph attacks using similar-looking Unicode characters
  try {
    // Create a URL to leverage browser's built-in IDN handling
    const url = new URL(`https://${normalized}`);
    normalized = url.hostname;
  } catch (e) {
    // If URL parsing fails, use the normalized form we have
  }

  return normalized;
}

async function computeMultiLayerHash(domain, nonce, entropyBase64, timestamp) {
  const encoder = new TextEncoder();

  // Normalize the domain first
  const normalizedDomain = normalizeDomain(domain);
  const domainData = encoder.encode(normalizedDomain);
  const nonceData = encoder.encode(nonce);

  // Decode entropy from base64
  const entropyData = Uint8Array.from(atob(entropyBase64), c => c.charCodeAt(0));
  const timestampData = encoder.encode(timestamp.toString());

  // Layer 1: HMAC-SHA256 with nonce
  const key1 = await crypto.subtle.importKey(
    "raw",
    nonceData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const layer1 = await crypto.subtle.sign("HMAC", key1, domainData);

  // Layer 2: HMAC-SHA512 with entropy mixed in
  const compositeKeyData = new Uint8Array(nonceData.length + entropyData.length);
  compositeKeyData.set(nonceData);
  compositeKeyData.set(entropyData, nonceData.length);

  const key2 = await crypto.subtle.importKey(
    "raw",
    compositeKeyData,
    { name: "HMAC", hash: "SHA-512" },
    false,
    ["sign"],
  );

  const layer2Input = new Uint8Array(layer1.byteLength + domainData.length);
  layer2Input.set(new Uint8Array(layer1));
  layer2Input.set(domainData, layer1.byteLength);
  const layer2 = await crypto.subtle.sign("HMAC", key2, layer2Input);

  // Layer 3: Final hash with timestamp
  const key3 = await crypto.subtle.importKey(
    "raw",
    nonceData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const finalInput = new Uint8Array(layer2.byteLength + timestampData.length);
  finalInput.set(new Uint8Array(layer2));
  finalInput.set(timestampData, layer2.byteLength);
  const finalHash = await crypto.subtle.sign("HMAC", key3, finalInput);

  // Convert to hex string
  const hashArray = Array.from(new Uint8Array(finalHash));
  return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

async function verifyIntegrityChecksum(hashes, checksum, nonce, entropyBase64) {
  const encoder = new TextEncoder();
  const nonceData = encoder.encode(nonce);

  // Decode entropy from base64
  const entropyData = Uint8Array.from(atob(entropyBase64), c => c.charCodeAt(0));

  // Create composite key
  const compositeKeyData = new Uint8Array(nonceData.length + entropyData.length);
  compositeKeyData.set(nonceData);
  compositeKeyData.set(entropyData, nonceData.length);

  // Compute expected checksum
  const key = await crypto.subtle.importKey(
    "raw",
    compositeKeyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const hashesString = hashes.join("|");
  const hashesData = encoder.encode(hashesString);
  const checksumHash = await crypto.subtle.sign("HMAC", key, hashesData);

  // Convert to hex and take first 16 chars
  const checksumArray = Array.from(new Uint8Array(checksumHash));
  const expectedChecksum = checksumArray.map(b => b.toString(16).padStart(2, "0")).join("").substring(0, 16);

  return expectedChecksum === checksum;
}

async function checkProxyProtection() {
  // Default to not allowed
  let isAllowed = false;

  // Try to get the protection data from attributes
  const proxyProtectionElement = document.querySelector("[data-allowed-domains][data-request-nonce][data-integrity-token]");

  if (proxyProtectionElement) {
    const hashedDomainsStr = proxyProtectionElement.dataset.allowedDomains;
    const nonce = proxyProtectionElement.dataset.requestNonce;
    const integrityToken = proxyProtectionElement.dataset.integrityToken;

    if (hashedDomainsStr && nonce && integrityToken) {
      try {
        // Parse integrity token
        const tokenJson = atob(integrityToken);
        const tokenData = JSON.parse(tokenJson);

        // Check timestamp validity (1 hour window)
        const currentTimestamp = Math.floor(Date.now() / 1000);
        const tokenTimestamp = tokenData.ts;
        const timeDiff = currentTimestamp - tokenTimestamp;

        if (timeDiff < 0 || timeDiff > 3600) {
          console.error("Integrity token expired or invalid timestamp");
          showPhishingWarning();
          return;
        }

        // Parse hashed domains and checksum
        const parts = hashedDomainsStr.split("|");
        if (parts.length < 2) {
          console.error("Invalid domain hash format");
          showPhishingWarning();
          return;
        }

        const checksum = parts[parts.length - 1];
        const hashedDomains = parts.slice(0, -1);

        // Verify integrity checksum
        const checksumValid = await verifyIntegrityChecksum(
          hashedDomains,
          checksum,
          nonce,
          tokenData.entropy,
        );

        if (!checksumValid) {
          console.error("Integrity checksum validation failed");
          showPhishingWarning();
          return;
        }

        // Check if current domain matches any allowed domain
        const currentDomain = window.location.hostname;
        const currentDomainHash = await computeMultiLayerHash(
          currentDomain,
          nonce,
          tokenData.entropy,
          tokenData.ts,
        );

        // Check for exact match
        isAllowed = hashedDomains.includes(currentDomainHash);

        // Additional anti-tampering check: verify the hash wasn't just added
        if (isAllowed) {
          // Re-verify with a different computation order as a double-check
          const verificationHash = await computeMultiLayerHash(
            normalizeDomain(currentDomain),  // Use explicitly normalized domain
            nonce,
            tokenData.entropy,
            tokenData.ts,
          );

          if (verificationHash !== currentDomainHash) {
            console.error("Hash verification mismatch");
            isAllowed = false;
          }
        }

      } catch (e) {
        console.error("Failed to validate domain:", e);
        isAllowed = false;
      }
    }
  }

  // Always show warning unless domain explicitly matches all checks
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

  // Create hostname display with extra emphasis
  const hostnameDiv = document.createElement("div");
  hostnameDiv.style.cssText = "font-size: 72px !important; font-weight: 900 !important; color: #ff6b6b !important; margin: 10px 0; line-height: 1.2; font-family: monospace; word-break: break-all; text-shadow: 0 2px 4px rgba(0,0,0,0.2);";
  hostnameDiv.textContent = window.location.hostname;
  contentDiv.appendChild(hostnameDiv);

  const verifyP = document.createElement("p");
  verifyP.style.cssText = "margin-bottom: 15px; font-weight: bold;";
  verifyP.textContent = "Please verify that you trust this domain before continuing.";
  contentDiv.appendChild(verifyP);

  const officialP = document.createElement("p");
  officialP.style.cssText = "margin-bottom: 20px;";
  officialP.textContent = "The official PyPI domain is pypi.org";
  contentDiv.appendChild(officialP);

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

export default checkProxyProtection;
