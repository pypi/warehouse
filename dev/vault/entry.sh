#!/bin/sh

# entry.sh: spawn vault
# taken and cleaned up from cabotage @ 6e7eafc:
# https://github.com/cabotage/cabotage-app/blob/6e7eafce737726a04bd6ce0896845f6cf2f7bd29/docker-compose/vault/entry.sh

export VAULT_ADDR=http://127.0.0.1:8200
if [ -f /vault/file/unseal ]; then
    echo "starting vault!"
    vault server \
        -dev -dev-skip-init -dev-listen-address="${VAULT_DEV_LISTEN_ADDRESS}" \
        -dev-root-token-id="${VAULT_DEV_ROOT_TOKEN_ID}" -config /etc/vault/config.hcl &
    echo "unsealing!"
    while true; do
        vault status >/dev/null 2>&1
        if [ $? = 2 ]; then
            echo "we good"
            break
        fi
        echo "vault not up yet..."
        sleep .5
    done
    UNSEAL_TOKEN=$(cat /vault/file/unseal)
    export UNSEAL_TOKEN
    vault operator unseal "${UNSEAL_TOKEN}"
    wait
else
    echo "starting vault!"
    vault server \
        -dev -dev-listen-address="${VAULT_DEV_LISTEN_ADDRESS}" \
        -dev-root-token-id="${VAULT_DEV_ROOT_TOKEN_ID}" -config /etc/vault/config.hcl 2>&1 \
            | tee "${HOME}/logfile" &
    while true; do
        if vault status >/dev/null 2>&1; then
            echo "we good"
            break
        fi
        echo "vault not up and initialized yet..."
        sleep .5
    done
    echo -n \
        "$(grep 'Unseal Key: ' "${HOME}/logfile" \
            | awk '{print $NF}' \
            | sed -r "s/\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]//g" \
        )" > /vault/file/unseal

    echo "bootstrapping our transit key"
    VAULT_TOKEN=${VAULT_DEV_ROOT_TOKEN_ID} \
        vault secrets enable transit

    wait
fi
