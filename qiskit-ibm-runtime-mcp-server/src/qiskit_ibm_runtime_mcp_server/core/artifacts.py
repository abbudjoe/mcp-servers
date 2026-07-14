# This code is part of Qiskit.
#
# (C) Copyright IBM 2026.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Artifact sink protocol and secure local content-addressed storage."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any, Protocol

from .models import ArtifactRef, InlineJsonValue
from .serialization import canonical_json, to_json_safe


_ARTIFACT_ID = re.compile(r"^sha256:([0-9a-f]{64})$")


class ArtifactError(RuntimeError):
    """Base error for artifact persistence and integrity failures."""


class ArtifactCollisionError(ArtifactError):
    """Raised when an existing digest path contains different bytes."""


class ArtifactIntegrityError(ArtifactError):
    """Raised when stored bytes do not match an artifact reference."""


class ArtifactPathError(ArtifactError):
    """Raised when a path could escape or traverse the configured CAS root."""


class ArtifactSink(Protocol):
    """Generic immutable byte sink used by the wrapper and its callers."""

    def put_bytes(
        self,
        data: bytes,
        *,
        kind: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        """Persist bytes and return their immutable reference."""
        ...

    def get_bytes(self, artifact: ArtifactRef) -> bytes:
        """Load and verify bytes for a reference."""
        ...


def content_id(data: bytes) -> str:
    """Return a content identifier for raw artifact bytes."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class LocalArtifactCAS:
    """Secure filesystem CAS with digest-only paths and collision checks."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser()
        self._create_safe_root(self._root)
        self._root = self._root.resolve(strict=True)
        root_stat = self._root.stat(follow_symlinks=False)
        self._root_identity = (root_stat.st_dev, root_stat.st_ino)

    @property
    def root(self) -> Path:
        """Return the normalized configured storage root."""
        return self._root

    @staticmethod
    def _create_safe_root(path: Path) -> None:
        """Create a root without accepting a symlink as the final component."""
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise ArtifactPathError(
                "artifact root must be a real directory, not a symlink"
            )
        root_stat = path.stat(follow_symlinks=False)
        if hasattr(os, "getuid") and root_stat.st_uid != os.getuid():
            raise ArtifactPathError("artifact root must be owned by the current user")
        path.chmod(0o700)

    def _assert_root_fd(self, root_fd: int) -> None:
        """Verify that a held directory handle still names the configured root."""
        descriptor_stat = os.fstat(root_fd)
        try:
            current_stat = self._root.stat(follow_symlinks=False)
        except OSError as exc:
            raise ArtifactPathError(
                "configured artifact root is no longer available"
            ) from exc
        if (
            not stat.S_ISDIR(descriptor_stat.st_mode)
            or (descriptor_stat.st_dev, descriptor_stat.st_ino) != self._root_identity
            or (current_stat.st_dev, current_stat.st_ino) != self._root_identity
        ):
            raise ArtifactPathError(
                "configured artifact root was replaced during operation"
            )

    def _open_root_fd(self) -> int:
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        )
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            root_fd = os.open(self._root, flags)
            self._assert_root_fd(root_fd)
        except OSError as exc:
            raise ArtifactPathError(
                "configured artifact root is unavailable or unsafe"
            ) from exc
        except Exception:
            os.close(root_fd)
            raise
        return root_fd

    @staticmethod
    def _filename_for(artifact_id: str) -> str:
        match = _ARTIFACT_ID.fullmatch(artifact_id)
        if match is None:
            raise ArtifactPathError(
                "artifact_id must be a lowercase sha256 content identifier"
            )
        return f"sha256-{match.group(1)}"

    @staticmethod
    def _read_regular_file(root_fd: int, filename: str) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(filename, flags, dir_fd=root_fd)
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                raise ArtifactPathError("artifact content must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)

    def put_bytes(
        self,
        data: bytes,
        *,
        kind: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        """Atomically persist bytes without trusting caller-controlled path data."""
        if not isinstance(data, bytes):
            raise TypeError("artifact data must be bytes")
        artifact_id = content_id(data)
        target = self._filename_for(artifact_id)
        root_fd = self._open_root_fd()
        try:
            try:
                existing = self._read_regular_file(root_fd, target)
            except FileNotFoundError:
                existing = None
            except OSError as exc:
                raise ArtifactCollisionError(
                    f"unsafe digest path for {artifact_id}"
                ) from exc
            if existing is not None:
                if existing != data:
                    raise ArtifactCollisionError(
                        f"digest path collision for {artifact_id}"
                    )
                self._assert_root_fd(root_fd)
                return self._reference(artifact_id, data, kind, media_type, metadata)

            temporary = f".incoming-{secrets.token_hex(16)}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temporary, flags, 0o600, dir_fd=root_fd)
            created_target = False
            try:
                with os.fdopen(descriptor, "wb", closefd=True) as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(
                        temporary,
                        target,
                        src_dir_fd=root_fd,
                        dst_dir_fd=root_fd,
                        follow_symlinks=False,
                    )
                    created_target = True
                except FileExistsError:
                    try:
                        existing = self._read_regular_file(root_fd, target)
                    except OSError as exc:
                        raise ArtifactCollisionError(
                            f"unsafe digest path for {artifact_id}"
                        ) from exc
                    if existing != data:
                        raise ArtifactCollisionError(
                            f"digest path collision for {artifact_id}"
                        ) from None
                try:
                    self._assert_root_fd(root_fd)
                except ArtifactPathError:
                    if created_target:
                        os.unlink(target, dir_fd=root_fd)
                    raise
                os.fsync(root_fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=root_fd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(root_fd)
        return self._reference(artifact_id, data, kind, media_type, metadata)

    def _reference(
        self,
        artifact_id: str,
        data: bytes,
        kind: str,
        media_type: str,
        metadata: dict[str, Any] | None,
    ) -> ArtifactRef:
        filename = self._filename_for(artifact_id)
        safe_metadata = to_json_safe(metadata or {})
        if not isinstance(
            safe_metadata, dict
        ):  # pragma: no cover - input type guarantees this
            raise TypeError("artifact metadata must be a JSON object")
        return ArtifactRef(
            schema_version="1.0",
            artifact_id=artifact_id,
            kind=kind,
            media_type=media_type,
            size_bytes=len(data),
            storage_uri=(self._root / filename).as_uri(),
            metadata=safe_metadata,
        )

    def get_bytes(self, artifact: ArtifactRef) -> bytes:
        """Load bytes and verify local locator, identifier, and declared size."""
        filename = self._filename_for(artifact.artifact_id)
        expected_uri = (self._root / filename).as_uri()
        if artifact.storage_uri != expected_uri:
            raise ArtifactIntegrityError(
                "artifact storage URI does not belong to this local CAS"
            )
        root_fd = self._open_root_fd()
        try:
            try:
                data = self._read_regular_file(root_fd, filename)
            except OSError as exc:
                raise ArtifactPathError(
                    "artifact path is unavailable or unsafe"
                ) from exc
            self._assert_root_fd(root_fd)
        finally:
            os.close(root_fd)
        if len(data) != artifact.size_bytes or content_id(data) != artifact.artifact_id:
            raise ArtifactIntegrityError(
                "stored artifact bytes failed size or digest verification"
            )
        return data


def artifactize(
    value: Any,
    sink: ArtifactSink,
    *,
    threshold_bytes: int,
    kind: str = "json",
    media_type: str = "application/json",
    metadata: dict[str, Any] | None = None,
) -> InlineJsonValue | ArtifactRef:
    """Inline a JSON-safe value or replace it with a CAS reference when large."""
    if threshold_bytes < 0:
        raise ValueError("threshold_bytes must be non-negative")
    safe_value = to_json_safe(value)
    encoded = canonical_json(safe_value)
    if len(encoded) <= threshold_bytes:
        return InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=safe_value,
        )
    artifact_metadata = {**(metadata or {}), "encoding": "canonical-json"}
    return sink.put_bytes(
        encoded,
        kind=kind,
        media_type=media_type,
        metadata=artifact_metadata,
    )
