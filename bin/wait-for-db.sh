#!/bin/bash

# healthy
# unhealthy
# starting

CONTAINER=warehouse_db_1
check() {
    docker inspect --format "{{.State.Health.Status }}" $CONTAINER
}

while [[ "$STATUS" != "healthy" ]]
do
    STATUS=$(check)
    echo "$STATUS ${SECONDS}"
    (( SECONDS > 60 )) && exit 1
    sleep 3
done
