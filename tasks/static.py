# Copyright 2013 Donald Stufft
#
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
import os.path
import shutil

import invoke


@invoke.task
def build():
    # Build our CSS files
    invoke.run("compass compile -c config.rb --force")


@invoke.task
def watch():
    try:
        # Watch With Compass
        invoke.run("compass watch -c config.rb")
    except KeyboardInterrupt:
        pass
