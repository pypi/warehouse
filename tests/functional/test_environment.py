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

import os

import platformdirs


def test_xdg_environment():
    # Backstop checks for Warehouse's (Dockerfile-configured) environment.
    # NOTE: We don't check the exact paths here, because they vary between
    # environments: they're in `$HOME` in local and CI builds, and in `/tmp`
    # when deployed.
    user_data = platformdirs.user_data_dir(ensure_exists=True)
    user_cache = platformdirs.user_cache_dir(ensure_exists=True)

    assert os.access(user_data, os.R_OK | os.W_OK)
    assert os.access(user_cache, os.R_OK | os.W_OK)
