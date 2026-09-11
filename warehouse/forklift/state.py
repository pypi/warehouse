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
import uuid

from hashlib import sha256
from typing import Any, Protocol

import automat


@dataclasses.dataclass(kw_only=True)
class FileUploadMechanism:
    name: str
    requires_processing: bool

    def prepare(self, file_upload_session_id):
        return {}


@dataclasses.dataclass(kw_only=True)
class HttpPostApplicationOctetFileUploadMechanism(FileUploadMechanism):
    name: str = "http-post-application-octet-stream"
    requires_processing: bool = False

    def prepare(self, file_upload_session_id):
        return {
            "upload-url": f"http://example.com/upload/{file_upload_session_id}",
        }


UPLOAD_MECHANISMS = {
    "http-post-application-octet-stream": HttpPostApplicationOctetFileUploadMechanism()
}


@dataclasses.dataclass(kw_only=True)
class FileUploadSession:
    filename: str
    size: int
    hashes: dict[str, str]
    metadata: str
    mechanism: FileUploadMechanism

    _upload_session_id = uuid.UUID

    expiration: datetime.datetime = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
        + datetime.timedelta(hours=1)
    )
    notices: list[str] = dataclasses.field(default_factory=list)
    mechanism_details: dict[Any, Any] = dataclasses.field(default_factory=dict)
    _id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)

    def serialize(self) -> dict[str, Any]:
        return {
            "valid-for": max(
                0, (self.expiration - datetime.datetime.now(datetime.UTC)).seconds
            ),
            "mechanism": {self.mechanism.name: self.mechanism_details},
        }

    def prepare(self):
        if self.mechanism:
            if not self.mechanism_details:
                self.mechanism_details = self.mechanism.prepare(self._id)
        else:
            raise RuntimeError("Mechanism not configured")


class FileUploadSessionController(Protocol):
    def serialize(self) -> dict[str, Any]:
        "Serialize the machine"

    def action_ready(self) -> None:
        "The File Upload Session was marked as ready"

    def action_cancel(self) -> None:
        "The File Upload Session was marked as canceled"

    def action_extend(self, seconds: int) -> None:
        "The File Upload Session was requested to be extended"

    def prepare(self) -> None:
        "Prepare the File Upload Session for upload"

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

    @pending.upon(FileUploadSessionController.serialize).loop()
    def serialize_pending(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ):
        return (
            file_upload_session.filename,
            file_upload_session.serialize() | {"status": "pending"},
        )

    @processing.upon(FileUploadSessionController.serialize).loop()
    def serialize_processing(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ):
        return (
            file_upload_session.filename,
            file_upload_session.serialize() | {"status": "processing"},
        )

    @complete.upon(FileUploadSessionController.serialize).loop()
    def serialize_complete(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ):
        return (
            file_upload_session.filename,
            file_upload_session.serialize() | {"status": "complete"},
        )

    @error.upon(FileUploadSessionController.serialize).loop()
    def serialize_error(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ):
        return (
            file_upload_session.filename,
            file_upload_session.serialize() | {"status": "error"},
        )

    @canceled.upon(FileUploadSessionController.serialize).loop()
    def serialize_canceled(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ):
        return (
            file_upload_session.filename,
            file_upload_session.serialize() | {"status": "canceled"},
        )

    @pending.upon(FileUploadSessionController.prepare).loop()
    def prepare(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ) -> None:
        file_upload_session.prepare()

    @pending.upon(FileUploadSessionController._process).to(processing)
    def _process(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ) -> None:
        pass

    @pending.upon(FileUploadSessionController._complete).to(complete)
    @processing.upon(FileUploadSessionController._complete).to(complete)
    def _complete(
        controller: FileUploadSessionController, file_upload_session: FileUploadSession
    ) -> None:
        pass

    @pending.upon(FileUploadSessionController.action_cancel).to(canceled)
    @processing.upon(FileUploadSessionController.action_cancel).to(canceled)
    @complete.upon(FileUploadSessionController.action_cancel).to(canceled)
    @error.upon(FileUploadSessionController.action_cancel).to(canceled)
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


@dataclasses.dataclass(kw_only=True)
class UploadSession:
    project: str
    version: str

    nonce: str = ""
    file_upload_sessions: list[FileUploadSession] = dataclasses.field(
        default_factory=list
    )
    notices: list[str] = dataclasses.field(default_factory=list)
    expiration: datetime.datetime = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
        + datetime.timedelta(days=1)
    )
    _token: str | None = None
    _id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)

    def serialize(self):
        return {
            "mechanisms": list(UPLOAD_MECHANISMS.keys()),
            "session-token": self.session_token,
            "valid-for": max(
                0, (self.expiration - datetime.datetime.now(datetime.UTC)).seconds
            ),
            "files": dict(
                [
                    file_upload_session.serialize()
                    for file_upload_session in self.file_upload_sessions
                ]
            ),
            "notices": self.notices,
        }

    def create_file_upload_session(
        self,
        filename: str,
        size: int,
        hashes: dict[str, str],
        metadata: str,
        mechanism: str,
    ):
        _mechanism = UPLOAD_MECHANISMS.get(mechanism)
        if _mechanism is None:
            raise KeyError(f'No mechanism "{mechanism}" available.')
        new_file_upload_session = FileUploadSessionFactory(
            FileUploadSession(
                filename=filename,
                size=size,
                hashes=hashes,
                metadata=metadata,
                mechanism=_mechanism,
            )
        )
        new_file_upload_session.prepare()
        self.file_upload_sessions.append(new_file_upload_session)
        return new_file_upload_session

    @property
    def has_errors(self):
        return len(self.notices) > 0

    @property
    def can_publish(self):
        return not any(
            [
                upload_session.serialize()["state"] in ["error", "pending"]
                for upload_session in self.file_upload_sessions
            ]
        )

    @property
    def session_token(self):
        if self._token is None:
            h = sha256()
            h.update(self.project.encode())
            h.update(self.version.encode())
            h.update(self.nonce.encode())
            self._token = h.hexdigest()
        return self._token


class UploadSessionController(Protocol):
    def create_file_upload_session(
        self,
        filename: str,
        size: int,
        hashes: dict[str, str],
        metadata: str,
        mechanism: str,
    ) -> None:
        "Create a new File Upload Session associated with this Upload Session"

    def action_publish(self) -> None:
        "The Upload Session was marked as published"

    def action_cancel(self) -> None:
        "The Upload Session was marked as canceled"

    def action_extend(self, seconds: int) -> None:
        "The Upload Session was requested to be extended"

    def _publish(self) -> None:
        "The Upload Session was published"

    def _clear_errors(self) -> None:
        "The Upload Session was revalidated"

    def _error(self, notice) -> None:
        "The Upload Session encountered an error"

    def _revalidate(self) -> None:
        "The Upload Session should be revalidated"

    def serialize(self) -> dict[str, Any]:
        "Serialize the machine"


def build_upload_session():
    builder = automat.TypeMachineBuilder(UploadSessionController, UploadSession)

    pending = builder.state("pending")
    published = builder.state("published")
    error = builder.state("error")
    canceled = builder.state("canceled")

    @pending.upon(UploadSessionController.serialize).loop()
    def serialize_pending(
        controller: UploadSessionController, upload_session: UploadSession
    ):
        return upload_session.serialize() | {"status": "pending"}

    @published.upon(UploadSessionController.serialize).loop()
    def serialize_published(
        controller: UploadSessionController, upload_session: UploadSession
    ):
        return upload_session.serialize() | {"status": "published"}

    @error.upon(UploadSessionController.serialize).loop()
    def serialize_error(
        controller: UploadSessionController, upload_session: UploadSession
    ):
        return upload_session.serialize() | {"status": "error"}

    @canceled.upon(UploadSessionController.serialize).loop()
    def serialize_canceled(
        controller: UploadSessionController, upload_session: UploadSession
    ):
        return upload_session.serialize() | {"status": "canceled"}

    @pending.upon(UploadSessionController.create_file_upload_session).loop()
    @error.upon(UploadSessionController.create_file_upload_session).loop()
    def create_file_upload_session(
        controller: UploadSessionController,
        upload_session: UploadSession,
        filename: str,
        size: int,
        hashes: dict[str, str],
        metadata: str,
        mechanism: str,
    ):
        try:
            return upload_session.create_file_upload_session(
                filename=filename,
                size=size,
                hashes=hashes,
                metadata=metadata,
                mechanism=mechanism,
            )
        except KeyError as e:
            controller._error(e)

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

    @error.upon(UploadSessionController._clear_errors).to(pending)
    def _clear_errors(
        controller: UploadSessionController, upload_session: UploadSession, notice: str
    ):
        pass

    @error.upon(UploadSessionController._revalidate).loop()
    def _revalidate(
        controller: UploadSessionController, upload_session: UploadSession, notice: str
    ):
        if not upload_session.has_errors:
            controller._clear_errors()

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

if __name__ == "__main__":
    import json

    upload_session = UploadSessionFactory(
        UploadSession(project="wutang", version="6.6.69")
    )
    print(upload_session.can_publish)
    print(json.dumps(upload_session.serialize()))
    file_upload_session = upload_session.create_file_upload_session(
        "wutang-6.6.69.tar.gz", 420, {}, "", "http-post-application-octet-stream"
    )
    print(upload_session.can_publish)
    print(json.dumps(upload_session.serialize()))
    file_upload_session.action_ready()
    print(upload_session.can_publish)
    print(json.dumps(upload_session.serialize()))
