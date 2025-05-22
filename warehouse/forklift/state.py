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

#######################################################################################
# This file demonstrates a Finite State Machine for the concepts of the File Upload
# Session and Upload Session defined in PEP 694.
#######################################################################################

import dataclasses
import datetime

from hashlib import sha256
from typing import Any, Protocol

import automat


@dataclasses.dataclass
class FileUploadMechanism:
    name: str
    requires_processing: bool


@dataclasses.dataclass
class FileUploadSession:
    mechanism: FileUploadMechanism

    expiration: datetime.datetime
    notices: list[str]
    mechanism_details: dict[Any, Any]


class FileUploadSessionController(Protocol):
    def action_ready(self) -> None:
        "The File Upload Session was marked as ready"

    def action_cancel(self) -> None:
        "The File Upload Session was marked as canceled"

    def action_extend(self, seconds: int) -> None:
        "The File Upload Session was requested to be extended"

    def _process(self) -> None:
        "The File Upload Session is processing a ready file upload"

    def _complete(self) -> None:
        "The File Upload Session is complete"

    def _error(self, notice) -> None:
        "The File Upload Session encountered an error"


def build_file_upload_session():

    builder = automat.TypeMachineBuilder(FileUploadSessionController, FileUploadSession)

    pending = builder.state("pending")
    processing = builder.state("processing")
    complete = builder.state("complete")
    error = builder.state("error")
    canceled = builder.state("canceled")

    @pending.upon(FileUploadSessionController._process).to(processing)
    def _process(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ) -> None:
        pass

    @pending.upon(FileUploadSessionController._complete).to(complete)
    def _complete(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ) -> None:
        pass

    @pending.upon(FileUploadSessionController.action_cancel).to(canceled)
    @processing.upon(FileUploadSessionController.action_cancel).to(canceled)
    @complete.upon(FileUploadSessionController.action_cancel).to(canceled)
    def action_cancel(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ) -> None:
        pass

    @pending.upon(FileUploadSessionController._error).to(error)
    @processing.upon(FileUploadSessionController._error).to(error)
    def _error(
        controller: FileUploadSessionController,
        file_upload_session: FileUploadSession,
        notice: str,
    ) -> None:
        file_upload_session.notices.append(notice)

    @pending.upon(FileUploadSessionController.action_ready).loop()
    def action_ready(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ) -> None:
        if file_upload_session.mechanism.requires_processing:
            controller._process()
        else:
            controller._complete()

    @pending.upon(FileUploadSessionController.action_extend).loop()
    def action_extend(
        controller: FileUploadSessionController,
        file_upload_session: FileUploadSession,
        seconds: int,
    ) -> None:
        if file_upload_session.expiration >= datetime.datetime.now(datetime.UTC):
            controller._error("Expired File Upload Sessions cannot be extended")
        else:
            file_upload_session.expiration = (
                file_upload_session.expiration + datetime.timedelta(seconds=seconds)
            )

    return builder.build()


FileUploadSessionFactory = build_file_upload_session()


@dataclasses.dataclass
class UploadSession:
    project: str
    version: str
    file_upload_sessions: list[FileUploadSession]

    expiration: datetime.datetime
    notices: list[str]

    nonce: str = ""

    @property
    def can_publish(self):
        return True

    @property
    def session_token(self):
        h = sha256()
        h.update(self.name.encode())
        h.update(self.version.encode())
        h.update(self.nonce.encode())
        return h.hexdigest()


class UploadSessionController(Protocol):
    def action_publish(self) -> None:
        "The Upload Session was marked as published"

    def action_cancel(self) -> None:
        "The Upload Session was marked as canceled"

    def action_extend(self, seconds: int) -> None:
        "The Upload Session was requested to be extended"

    def _publish(self) -> None:
        "The Upload Session was published"

    def _error(self, notice) -> None:
        "The Upload Session encountered an error"


def build_upload_session():
    builder = automat.TypeMachineBuilder(UploadSessionController, UploadSession)

    pending = builder.state("pending")
    published = builder.state("published")
    error = builder.state("error")
    canceled = builder.state("canceled")

    @pending.upon(UploadSessionController.action_publish).loop()
    def action_publish(
        controller: UploadSessionController, upload_session: UploadSession
    ):
        if upload_session.can_publish:
            controller._publish()
        else:
            controller._error("Upload Session could not be published")

    @pending.upon(UploadSessionController.action_cancel).to(canceled)
    @error.upon(UploadSessionController.action_cancel).to(canceled)
    def action_cancel(
        controller: UploadSessionController, upload_session: UploadSession
    ):
        pass

    @pending.upon(UploadSessionController._error).to(error)
    def _error(
        controller: UploadSessionController, upload_session: UploadSession, notice: str
    ):
        upload_session.notices.append(notice)

    @pending.upon(UploadSessionController._publish).to(published)
    def _publish(controller: UploadSessionController, upload_session: UploadSession):
        pass

    @pending.upon(UploadSessionController.action_extend).loop()
    def action_extend(
        controller: UploadSessionController,
        upload_session: UploadSession,
        seconds: int,
    ) -> None:
        if upload_session.expiration >= datetime.datetime.now(datetime.UTC):
            controller._error("Expired Upload Sessions cannot be extended")
        else:
            upload_session.expiration = upload_session.expiration + datetime.timedelta(
                seconds=seconds
            )

    return builder.build()


UploadSessionFactory = build_upload_session()
