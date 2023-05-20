# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import asyncudp
import os
import sys


async def main(host, port, output):
    sock = await asyncudp.create_socket(local_addr=(host, port))
    print(f"Listening on udp {host}:{port}. Displaying metrics: {output}")

    while True:
        data, _ = await sock.recvfrom()
        if output:
            message = data.decode().strip()
            print(message)

if __name__ == '__main__':
    try:
        host, port = sys.argv[1].split(":")
        port = int(port)
    except (ValueError, IndexError):
        print("Usage: python3 notdatadog.py <host>:<port>")
        sys.exit(1)
    output = os.environ.get("METRICS_OUTPUT", "").lower() == "true"
    asyncio.run(main(host, port, output))
