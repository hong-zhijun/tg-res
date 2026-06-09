import os
import shutil
from pathlib import Path


def safe_filename(name: str, fallback: str = "file") -> str:
    cleaned = "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip(" .")
    return cleaned[:120] or fallback


def build_save_path(
    type_: str,
    msg_id: int,
    unique_id: str,
    ext: str,
    original_name: str | None = None,
    group_path: str | None = None,
) -> str:
    safe_unique = "".join(c for c in unique_id if c.isalnum() or c in "-_")[:32]
    if original_name:
        original = safe_filename(Path(original_name).name)
        filename = f"{msg_id}_{original}"
        if not Path(filename).suffix and ext:
            filename += ext
    else:
        filename = f"{msg_id}_{safe_unique}{ext}"
    folder = group_path.strip("/") if group_path else type_
    return os.path.join(folder, filename)


def ensure_disk_space(path: str, needed_bytes: int, buffer_mb: int = 100) -> None:
    stat = shutil.disk_usage(path)
    if stat.free < needed_bytes + buffer_mb * 1024 * 1024:
        raise OSError(
            f"Insufficient disk space: need {needed_bytes} bytes + {buffer_mb}MB buffer, "
            f"have {stat.free} bytes"
        )
