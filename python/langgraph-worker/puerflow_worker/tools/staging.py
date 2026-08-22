from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from puerflow_worker.sandbox import SandboxClient

_MAX_FILES = 32
_MAX_BYTES = 200_000


def _safe_path(path: str) -> bool:
    cleaned = (path or "").replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        return False
    return True


@dataclass
class FileFingerprint:
    path: str
    size: int
    modified_time: int
    digest: str
    content: str


async def snapshot_workspace(sandbox: SandboxClient, session_id: str, user_id: str = "") -> list[FileFingerprint]:
    entries = await sandbox.file_list("", session_id=session_id, user_id=user_id, recursive=True)
    snaps: list[FileFingerprint] = []
    for item in entries:
        path = str(item.get("path") or item.get("name") or "")
        if not item.get("is_file", True) or not _safe_path(path):
            continue
        read = await sandbox.file_read(path, session_id=session_id, user_id=user_id)
        if not read.success:
            continue
        content = read.content or ""
        if len(content.encode("utf-8")) > _MAX_BYTES:
            continue
        snaps.append(
            FileFingerprint(
                path=path,
                size=int(item.get("size_bytes") or len(content)),
                modified_time=int(item.get("modified_time") or 0),
                digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                content=content,
            )
        )
        if len(snaps) >= _MAX_FILES:
            break
    return snaps


def changed_paths(before: list[FileFingerprint], after: list[FileFingerprint]) -> set[str]:
    before_map = {item.path: item for item in before}
    after_map = {item.path: item for item in after}
    changed = set()
    for path, item in after_map.items():
        prev = before_map.get(path)
        if prev is None or prev.digest != item.digest:
            changed.add(path)
    for path in before_map:
        if path not in after_map:
            changed.add(path)
    return changed


async def restore_workspace(
    sandbox: SandboxClient,
    before: list[FileFingerprint],
    after: list[FileFingerprint],
    session_id: str,
    user_id: str = "",
) -> None:
    before_map = {item.path: item for item in before}
    after_map = {item.path: item for item in after}
    for path, item in after_map.items():
        if path not in before_map:
            await sandbox.file_delete(path, session_id=session_id, user_id=user_id)
    for path, item in before_map.items():
        current = after_map.get(path)
        if current is None or current.digest != item.digest:
            await sandbox.file_write(path, item.content, session_id=session_id, user_id=user_id)
