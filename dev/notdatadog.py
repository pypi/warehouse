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

import asyncore
import socket
import smtpd


class AsyncoreSocketUDP(asyncore.dispatcher):
    def __init__(self, host="127.0.0.1", port=8125):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"Listening on udp {host}:{port}")
        self.bind((host, port))

    def handle_connect(self):
        print("Server Started...")

    def handle_read(self):
        data = self.recv(8 * 1024)
        print(data)

    def handle_write(self):
        pass

    def writable(self):
        return False


if __name__ == "__main__":
    options = smtpd.parseargs()
    AsyncoreSocketUDP(options.localhost, options.localport)
    asyncore.loop()
