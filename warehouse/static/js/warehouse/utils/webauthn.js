/* Licensed under the Apache License, Version 2.0 (the "License");
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


const populateWebAuthnErrorList = (errors) => {
  const errorList = document.getElementById("webauthn-errors");
  if (errorList === null) {
    return;
  }

  errorList.innerHTML = "";

  errors.forEach((error) => {
    const errorItem = document.createElement("li");
    errorItem.appendChild(document.createTextNode(error));
    errorList.appendChild(errorItem);
  });
};

const doWebAuthn = (buttonId, func) => {
  const webAuthnButton = document.getElementById(buttonId);
  if (webAuthnButton === null) {
    return null;
  }

  const csrfToken = webAuthnButton.getAttribute("csrf-token");
  if (csrfToken === null) {
    return;
  }

  if (!window.PublicKeyCredential) {
    populateWebAuthnErrorList(["Your browser doesn't support WebAuthn."]);
    return;
  }

  webAuthnButton.disabled = false;
  webAuthnButton.addEventListener("click", async () => { func(csrfToken); });
};

const hexEncode = (buf) => {
  return Array.from(buf).map((x) => {
    return ("0" + x.toString(16)).substr(-2);
  }).join("");
};

const webAuthnBtoA = (encoded) => {
  return btoa(encoded).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
};

const webAuthnBase64Normalize = (encoded) => {
  return encoded.replace(/_/g, "/").replace(/-/g, "+");
};

const transformAssertionOptions = (assertionOptions) => {
  let {challenge, allowCredentials} = assertionOptions;

  challenge = Uint8Array.from(challenge, c => c.charCodeAt(0));
  allowCredentials = allowCredentials.map(credentialDescriptor => {
    let {id} = credentialDescriptor;
    id = webAuthnBase64Normalize(id);
    id = Uint8Array.from(atob(id), c => c.charCodeAt(0));
    return Object.assign({}, credentialDescriptor, {id});
  });

  const transformedOptions = Object.assign(
    {},
    assertionOptions,
    {challenge, allowCredentials});

  return transformedOptions;
};

const transformAssertion = (assertion) => {
  const authData = new Uint8Array(assertion.response.authenticatorData);
  const clientDataJSON = new Uint8Array(assertion.response.clientDataJSON);
  const rawId = new Uint8Array(assertion.rawId);
  const sig = new Uint8Array(assertion.response.signature);
  const assertionClientExtensions = assertion.getClientExtensionResults();

  return {
    id: assertion.id,
    rawId: webAuthnBtoA(rawId),
    type: assertion.type,
    authData: webAuthnBtoA(String.fromCharCode(...authData)),
    clientData: webAuthnBtoA(String.fromCharCode(...clientDataJSON)),
    signature: hexEncode(sig),
    assertionClientExtensions: JSON.stringify(assertionClientExtensions),
  };
};

const transformCredentialOptions = (credentialOptions) => {
  let {challenge, user} = credentialOptions;
  user.id = Uint8Array.from(credentialOptions.user.id, c => c.charCodeAt(0));
  challenge = Uint8Array.from(credentialOptions.challenge, c => c.charCodeAt(0));

  const transformedOptions = Object.assign({}, credentialOptions, {challenge, user});

  return transformedOptions;
};

const transformCredential = (credential) => {
  const attObj = new Uint8Array(credential.response.attestationObject);
  const clientDataJSON = new Uint8Array(credential.response.clientDataJSON);
  const rawId = new Uint8Array(credential.rawId);
  const registrationClientExtensions = credential.getClientExtensionResults();

  return {
    id: credential.id,
    rawId: webAuthnBtoA(rawId),
    type: credential.type,
    attObj: webAuthnBtoA(String.fromCharCode(...attObj)),
    clientData: webAuthnBtoA(String.fromCharCode(...clientDataJSON)),
    registrationClientExtensions: JSON.stringify(registrationClientExtensions),
  };
};

const postCredential = async (label, credential, token) => {
  const formData = new FormData();
  formData.set("label", label);
  formData.set("credential", JSON.stringify(credential));
  formData.set("csrf_token", token);

  const resp = await fetch(
    "/manage/account/webauthn-provision/validate", {
      method: "POST",
      cache: "no-cache",
      body: formData,
    }
  );

  return await resp.json();
};

const postAssertion = async (assertion, token) => {
  const formData = new FormData();
  formData.set("credential", JSON.stringify(assertion));
  formData.set("csrf_token", token);

  const resp = await fetch(
    "/account/webauthn-authenticate/validate" + window.location.search, {
      method: "POST",
      cache: "no-cache",
      body: formData,
    }
  );

  return await resp.json();
};

export const ProvisionWebAuthn = () => {
  doWebAuthn("webauthn-provision-begin", async (csrfToken) => {
    const label = document.getElementById("webauthn-provision-label").value;

    // TODO(ww): Should probably find a way to use the route string here,
    // not the actual endpoint.
    const resp = await fetch(
      "/manage/account/webauthn-provision/options", {
        cache: "no-cache",
      }
    );

    const credentialOptions = await resp.json();
    const transformedOptions = transformCredentialOptions(credentialOptions);
    const credential = await navigator.credentials.create({
      publicKey: transformedOptions,
    });
    const transformedCredential = transformCredential(credential);

    const status = await postCredential(label, transformedCredential, csrfToken);
    if (status.fail) {
      populateWebAuthnErrorList(status.fail.errors);
      return;
    }

    window.location.replace("/manage/account");
  });
};

export const AuthenticateWebAuthn = () => {
  doWebAuthn("webauthn-auth-begin", async (csrfToken) => {
    const resp = await fetch(
      "/account/webauthn-authenticate/options" + window.location.search, {
        cache: "no-cache",
      }
    );

    const assertionOptions = await resp.json();
    if (assertionOptions.fail) {
      window.location.replace("/account/login");
      return;
    }

    const transformedOptions = transformAssertionOptions(assertionOptions);
    const assertion = await navigator.credentials.get({
      publicKey: transformedOptions,
    });
    const transformedAssertion = transformAssertion(assertion);

    const status = await postAssertion(transformedAssertion, csrfToken);
    if (status.fail) {
      populateWebAuthnErrorList(status.fail.errors);
      return;
    }

    window.location.replace(status.redirect_to);
  });
};
