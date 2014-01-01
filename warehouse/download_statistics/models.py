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


class DownloadStatisticsModels(object):
    def __init__(self, engine):
        self._engine = engine

    def create_download(self, package_name, package_version, distribution_type,
                        python_type, python_release, python_version,
                        installer_type, installer_version, operating_system,
                        operating_system_version, download_time,
                        raw_user_agent):

        from warehouse.download_statistics.tables import downloads

        return self._engine.execute(downloads.insert().values(
            package_name=package_name,
            package_version=package_version,
            distribution_type=distribution_type,
            python_type=python_type,
            python_release=python_release,
            python_version=python_version,
            installer_type=installer_type,
            installer_version=installer_version,
            operating_system=operating_system,
            operating_system_version=operating_system_version,
            download_time=download_time,
            raw_user_agent=raw_user_agent,
        ))
