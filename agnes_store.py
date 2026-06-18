"""
Agnes 历史画廊持久化存储

用 SQLite 存储生成历史，图片文件存到用户数据目录，数据库记录元信息。
- 线程安全：每个连接独立，调用方按需创建/关闭。
- 自带缩略图缓存，便于 UI 快速加载。
"""

from __future__ import annotations

import io
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import platformdirs
from PIL import Image

APP_NAME = "AgnesImageStudio"
# 用户数据目录（跨平台）：Win 下为 %LOCALAPPDATA%\AgnesImageStudio
DATA_DIR = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
IMAGES_DIR = DATA_DIR / "images"
THUMBS_DIR = DATA_DIR / "thumbs"
DB_PATH = DATA_DIR / "history.db"

THUMB_SIZE = (200, 200)


def _ensure_dirs():
    for d in (DATA_DIR, IMAGES_DIR, THUMBS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class HistoryItem:
    id: int | None
    prompt: str
    mode: str                      # txt2img / img2img / variation
    size: str
    image_path: str                # 原图相对路径（相对 IMAGES_DIR）
    thumb_path: str                # 缩略图相对路径
    width: int
    height: int
    fmt: str
    revised_prompt: str | None
    url: str | None
    reference_image: str | None    # 参考图的 base64 快照（可选，仅记录用）
    params: str                    # JSON 字符串，存额外参数（n/timeout/等）
    created_at: float              # unix 时间戳
    favorite: int = 0              # 0/1


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class HistoryStore:
    """SQLite 历史存储。一个实例对应一个连接，加锁保证线程安全。"""

    def __init__(self, db_path: Path = DB_PATH):
        _ensure_dirs()
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt          TEXT NOT NULL,
                mode            TEXT NOT NULL,
                size            TEXT NOT NULL,
                image_path      TEXT NOT NULL,
                thumb_path      TEXT NOT NULL,
                width           INTEGER,
                height          INTEGER,
                fmt             TEXT,
                revised_prompt  TEXT,
                url             TEXT,
                reference_image TEXT,
                params          TEXT,
                created_at      REAL NOT NULL,
                favorite        INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_history_fav ON history(favorite, created_at DESC);
            """)

    # ---- 写入 ----

    def _make_thumbnail(self, image_bytes: bytes, name: str) -> tuple[str, str, int, int, str]:
        """生成原图文件 + 缩略图，返回 (image_rel, thumb_rel, w, h, fmt)。"""
        pil = Image.open(io.BytesIO(image_bytes))
        w, h = pil.size
        fmt = (pil.format or "PNG").upper()

        ext = "png"
        if fmt == "JPEG":
            ext = "jpg"
        img_name = f"{name}.{ext}"
        thumb_name = f"{name}.png"

        # 原图
        (IMAGES_DIR / img_name).write_bytes(image_bytes)

        # 缩略图（统一 PNG，便于快速加载）
        thumb = pil.copy()
        thumb.thumbnail(THUMB_SIZE)
        if thumb.mode != "RGB":
            thumb = thumb.convert("RGB")
        thumb.save(IMAGES_DIR.parent / THUMBS_DIR / thumb_name, format="PNG")

        return img_name, thumb_name, w, h, fmt

    def add(self, *, prompt: str, mode: str, size: str, image_bytes: bytes,
            revised_prompt: str | None = None, url: str | None = None,
            reference_image: str | None = None, params: dict | None = None) -> HistoryItem:
        """保存一张生成结果到历史。"""
        with self._lock:
            name = f"{int(time.time()*1000)}"
            img_rel, thumb_rel, w, h, fmt = self._make_thumbnail(image_bytes, name)
            ts = time.time()
            self._conn.execute(
                """INSERT INTO history
                   (prompt, mode, size, image_path, thumb_path, width, height, fmt,
                    revised_prompt, url, reference_image, params, created_at, favorite)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                (prompt, mode, size, img_rel, thumb_rel, w, h, fmt,
                 revised_prompt, url, reference_image,
                 json.dumps(params or {}, ensure_ascii=False), ts),
            )
            self._conn.commit()
            cur = self._conn.execute("SELECT last_insert_rowid()")
            row_id = cur.fetchone()[0]
            return self._row_to_item(self._conn.execute(
                "SELECT * FROM history WHERE id=?", (row_id,)).fetchone())

    # ---- 查询 ----

    def _row_to_item(self, row: sqlite3.Row) -> HistoryItem:
        return HistoryItem(
            id=row["id"], prompt=row["prompt"], mode=row["mode"], size=row["size"],
            image_path=row["image_path"], thumb_path=row["thumb_path"],
            width=row["width"], height=row["height"], fmt=row["fmt"],
            revised_prompt=row["revised_prompt"], url=row["url"],
            reference_image=row["reference_image"], params=row["params"],
            created_at=row["created_at"], favorite=row["favorite"],
        )

    def list_all(self, favorites_only: bool = False, limit: int = 500) -> list[HistoryItem]:
        with self._lock:
            if favorites_only:
                sql = "SELECT * FROM history WHERE favorite=1 ORDER BY created_at DESC LIMIT ?"
            else:
                sql = "SELECT * FROM history ORDER BY created_at DESC LIMIT ?"
            rows = self._conn.execute(sql, (limit,)).fetchall()
            return [self._row_to_item(r) for r in rows]

    def search(self, keyword: str, limit: int = 200) -> list[HistoryItem]:
        with self._lock:
            kw = f"%{keyword}%"
            rows = self._conn.execute(
                "SELECT * FROM history WHERE prompt LIKE ? ORDER BY created_at DESC LIMIT ?",
                (kw, limit)).fetchall()
            return [self._row_to_item(r) for r in rows]

    def get(self, item_id: int) -> HistoryItem | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM history WHERE id=?", (item_id,)).fetchone()
            return self._row_to_item(row) if row else None

    def set_favorite(self, item_id: int, favorite: bool):
        with self._lock:
            self._conn.execute("UPDATE history SET favorite=? WHERE id=?",
                               (1 if favorite else 0, item_id))
            self._conn.commit()

    def delete(self, item_id: int):
        """删除一条记录及其图片文件。"""
        with self._lock:
            row = self._conn.execute("SELECT * FROM history WHERE id=?", (item_id,)).fetchone()
            if not row:
                return
            # 删文件
            for rel, base in ((row["image_path"], IMAGES_DIR), (row["thumb_path"], THUMBS_DIR)):
                p = base / rel
                try:
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass
            self._conn.execute("DELETE FROM history WHERE id=?", (item_id,))
            self._conn.commit()

    def clear_all(self):
        with self._lock:
            self._conn.execute("DELETE FROM history")
            self._conn.commit()
        for d in (IMAGES_DIR, THUMBS_DIR):
            for p in d.glob("*"):
                try:
                    p.unlink()
                except OSError:
                    pass

    # ---- 路径辅助 ----

    @staticmethod
    def image_fullpath(item: HistoryItem) -> Path:
        return IMAGES_DIR / item.image_path

    @staticmethod
    def thumb_fullpath(item: HistoryItem) -> Path:
        return THUMBS_DIR / item.thumb_path

    def close(self):
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# 配置存储（简单的 JSON）
# ---------------------------------------------------------------------------

class ConfigStore:
    """应用配置（API Key、设置等）的 JSON 持久化。"""

    def __init__(self):
        _ensure_dirs()
        self.path = DATA_DIR / "config.json"
        self._data: dict = {}
        self._lock = threading.Lock()
        self.load()

    def load(self):
        with self._lock:
            if self.path.exists():
                try:
                    self._data = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    self._data = {}

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self) -> dict:
        with self._lock:
            return dict(self._data)
