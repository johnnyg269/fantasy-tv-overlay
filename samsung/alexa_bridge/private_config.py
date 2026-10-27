"""Read owner-only configuration without logging credential material."""

import json
import os
from pathlib import Path
import stat


def load_private_json(path, max_bytes=65536):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Configuration must be a regular file owned by this user")
    if info.st_mode & 0o077:
        raise ValueError("Configuration permissions must be 0600")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
                or opened.st_mode & 0o077 or opened.st_ino != info.st_ino
                or opened.st_dev != info.st_dev):
            raise ValueError("Configuration changed while opening or is not private")
        if opened.st_size > max_bytes:
            raise ValueError("Configuration exceeds the bounded size")
        content = stream.read(max_bytes + 1)
        if len(content.encode("utf-8")) > max_bytes:
            raise ValueError("Configuration exceeds the bounded size")
        try:
            data = json.loads(content)
        except RecursionError:
            raise ValueError("Configuration is too deeply nested") from None
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object")
    return data
