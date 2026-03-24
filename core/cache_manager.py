"""File-based cache for pipeline stages.

Each video's results are cached so failed runs can resume
from the last successful stage.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".cutpilot" / "cache"


class CacheManager:
    """File-based cache keyed by (video_path, stage).

    Cache layout:
        base_dir / {md5_prefix} / {stage}.json
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or _DEFAULT_CACHE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _cache_path(self, video_path: Path, stage: str) -> Path:
        """Build deterministic cache path for a video + stage.

        Uses ``{video_name}_{file_size}`` hashed to md5[:12] as the
        directory name, with ``{stage}.json`` as the filename.
        """
        video_path = Path(video_path)
        file_size = video_path.stat().st_size if video_path.exists() else 0
        key = f"{video_path.name}_{file_size}"
        digest = hashlib.md5(key.encode()).hexdigest()[:12]
        return self._base_dir / digest / f"{stage}.json"

    def exists(self, video_path: Path, stage: str) -> bool:
        """Return True if cached data exists for *video_path* / *stage*."""
        return self._cache_path(video_path, stage).is_file()

    def load(self, video_path: Path, stage: str) -> Any:
        """Read and deserialise cached JSON for *video_path* / *stage*.

        Raises:
            FileNotFoundError: If the cache entry does not exist.
            json.JSONDecodeError: If the cached file is corrupt.
        """
        cache_file = self._cache_path(video_path, stage)
        data = cache_file.read_text(encoding="utf-8")
        return json.loads(data)

    def save(self, video_path: Path, stage: str, data: Any) -> None:
        """Serialise *data* as JSON and write to the cache."""
        cache_file = self._cache_path(video_path, stage)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("Cached stage '%s' for %s", stage, video_path)

    def clear(self, video_path: Path) -> None:
        """Remove the entire cache directory for *video_path*."""
        # Derive the directory from any stage (parent is the same)
        cache_dir = self._cache_path(video_path, "_probe").parent
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            logger.info("Cleared cache for %s", video_path)

    def clear_all(self) -> None:
        """Remove the entire cache base directory."""
        if self._base_dir.exists():
            shutil.rmtree(self._base_dir)
            logger.info("Cleared all cache at %s", self._base_dir)
