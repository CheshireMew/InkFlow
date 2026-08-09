from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    config_dir: Path
    cache_dir: Path

    @classmethod
    def resolve(cls, *, override_data_dir: Path | None = None) -> "AppPaths":
        if override_data_dir:
            data_dir = override_data_dir.resolve()
            config_dir = data_dir / "config"
            cache_dir = data_dir / "cache"
        else:
            dirs = PlatformDirs(appname="InkFlow", appauthor=False, roaming=False)
            data_dir = Path(dirs.user_data_path)
            config_dir = Path(dirs.user_config_path)
            cache_dir = Path(dirs.user_cache_path)
        for path in (data_dir, config_dir, cache_dir):
            path.mkdir(parents=True, exist_ok=True)
        return cls(data_dir=data_dir, config_dir=config_dir, cache_dir=cache_dir)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "inkflow.sqlite3"
