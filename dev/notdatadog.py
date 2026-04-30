# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
import sys

import asyncudp


async def main(host, port, output):
    sock = await asyncudp.create_socket(local_addr=(host, port))
    print(f"Listening on udp {host}:{port}. Displaying metrics: {output}")

    while True:
        data, _ = await sock.recvfrom()
        if output:
            message = data.decode().strip()
            print(message)


if __name__ == "__main__":
    try:
        host, port = sys.argv[1].split(":")
        port = int(port)
    except (ValueError, IndexError):
        print("Usage: python3 notdatadog.py <host>:<port>")
        sys.exit(1)
    output = os.environ.get("METRICS_OUTPUT", "").lower() == "true"
    asyncio.run(main(host, port, output))
