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

    errors.forEach(function(error) {
        const errorItem = document.createElement("li");
        errorItem.appendChild(document.createTextNode(error));
        errorList.appendChild(errorItem);
    });
}

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
}

const webAuthnBtoA = (encoded) => {
    return btoa(encoded).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

const transformCredentialOptions = (credentialOptions) => {
    let {challenge, user} = credentialOptions;
    user.id = Uint8Array.from(credentialOptions.user.id, c => c.charCodeAt(0));
    challenge = Uint8Array.from(credentialOptions.challenge, c => c.charCodeAt(0));

    const transformedOptions = Object.assign({}, credentialOptions, {challenge, user});

    return transformedOptions;
}

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
}

const postCredential = async (credential, token) => {
    const formData = new FormData();
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
}

export const ProvisionWebAuthn = () => {
    doWebAuthn("webauthn-provision-begin", async (csrfToken) => {
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
            publicKey: transformedOptions
        });

        const transformedCredential = transformCredential(credential);
        const status = await postCredential(transformedCredential, csrfToken);
        if (status.fail) {
            populateWebAuthnErrorList(status.fail.errors);
            return;
        }

        window.location.replace("/manage/account");
    });
};

export const AuthenticateWebAuthn = () => {
    doWebAuthn("webauthn-auth-begin", async (csrfToken) => {
        return;
    });
};
