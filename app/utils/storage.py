import os
import shutil


def build_save_path(type_: str, msg_id: int, unique_id: str, ext: str) -> str:
    safe_unique = "".join(c for c in unique_id if c.isalnum() or c in "-_")[:32]
    filename = f"{msg_id}_{safe_unique}{ext}"
    return os.path.join(type_, filename)


def ensure_disk_space(path: str, needed_bytes: int, buffer_mb: int = 100) -> None:
    stat = shutil.disk_usage(path)
    if stat.free < needed_bytes + buffer_mb * 1024 * 1024:
        raise OSError(
            f"Insufficient disk space: need {needed_bytes} bytes + {buffer_mb}MB buffer, "
            f"have {stat.free} bytes"
        )
