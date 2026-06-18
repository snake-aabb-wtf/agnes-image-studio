"""
Agnes Image Studio — PySide6 图片生成器 (主程序)

三栏专业界面：
  左栏：参数面板（API Key、模式切换、Prompt、尺寸、张数、参考图拖拽、生成）
  中栏：大图预览（滚轮缩放、拖拽平移、双击自适应）+ revised_prompt
  右栏：历史画廊（缩略图、复用参数、生成变体、收藏、搜索）

功能：文生图 / 图生图 / 变体 / 批量(1-4张) / 历史画廊(SQLite) /
      提示词模板与收藏 / 复制剪贴板 / 另存为 / 深色主题 / 设置面板

启动：python agnes_gui.py
"""

from __future__ import annotations

import io
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThread, Signal, QSize, QPoint, QPointF, QRectF, QTimer, QBuffer, QMimeData,
)
from PySide6.QtGui import (
    QAction, QPixmap, QImage, QPainter, QWheelEvent, QMouseEvent, QIcon,
    QKeySequence, QShortcut, QColor, QFont, QPalette, QDragEnterEvent, QDropEvent,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QStatusBar, QProgressBar, QGroupBox, QScrollArea,
    QGridLayout, QListWidget, QListWidgetItem, QMenu, QToolButton, QSizePolicy,
    QDialog, QFormLayout, QDialogButtonBox, QFrame, QSlider, QSpacerItem,
)

import qtawesome as qta

from agnes_client import (
    AgnesClient, GenerateRequest, GeneratedImage, AgnesAPIError,
    DEFAULT_SIZE, DEFAULT_TIMEOUT, MIN_TIMEOUT, MAX_TIMEOUT, MODEL, MODELS,
)
from agnes_store import HistoryStore, ConfigStore, HistoryItem

# ===========================================================================
# 提示词模板（内置风格）
# ===========================================================================

BUILTIN_TEMPLATES = [
    ("电影感", "cinematic film still, dramatic lighting, shallow depth of field, 35mm, highly detailed, 8k"),
    ("动漫风", "anime style, vibrant colors, cel shading, studio ghibli inspired, detailed background"),
    ("二次元", "2d anime illustration, beautiful detailed eyes, fine line art, vivid colors, soft lighting, masterpiece, best quality, highres"),
    ("写实摄影", "photorealistic, ultra detailed, professional photography, natural lighting, 8k uhd"),
    ("3D 渲染", "3d render, octane render, ray tracing, soft global illumination, hyperrealistic materials"),
    ("水彩画", "watercolor painting, soft brush strokes, artistic, paper texture, pastel colors"),
    ("油画", "oil painting, thick brush strokes, classical art style, rich textures, masterpiece"),
    ("赛博朋克", "cyberpunk, neon lights, futuristic city, rain, blade runner aesthetic, ultra detailed"),
    ("像素艺术", "pixel art, 16-bit retro game style, vibrant palette, detailed sprite"),
    ("低多边形", "low poly 3d art, flat shading, minimalistic, geometric, clean design"),
    ("概念艺术", "concept art, digital painting, fantasy, epic scale, trending on artstation"),
]

# 尺寸预设
SIZE_PRESETS = [
    ("正方形 1024²", "1024x1024"),
    ("横向 1792×1024", "1792x1024"),
    ("纵向 1024×1792", "1024x1792"),
    ("横向 1536×1024", "1536x1024"),
    ("纵向 1024×1536", "1024x1536"),
    ("横向 1280×720", "1280x720"),
    ("纵向 720×1280", "720x1280"),
]


# ===========================================================================
# 全局样式（深色主题）
# ===========================================================================

DARK_QSS = """
QMainWindow, QDialog { background-color: #1e1e2e; }
QWidget { color: #cdd6f4; font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif; font-size: 13px; }

QLabel { background: transparent; }
QLabel#titleLabel { font-size: 18px; font-weight: bold; color: #89b4fa; }
QLabel#hintLabel { color: #6c7086; font-size: 11px; }
QLabel#infoLabel { color: #a6adc8; font-size: 11px; }

QGroupBox {
    border: 1px solid #313244; border-radius: 8px;
    margin-top: 14px; padding: 10px 8px 8px 8px;
    background-color: #181825;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #89b4fa; font-weight: bold; }

QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background-color: #313244; border: 1px solid #45475a; border-radius: 6px;
    padding: 6px 8px; selection-background-color: #89b4fa; color: #cdd6f4;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #89b4fa; }
QTextEdit { font-size: 13px; line-height: 1.4; }

QPushButton {
    background-color: #45475a; border: 1px solid #585b70; border-radius: 6px;
    padding: 7px 14px; color: #cdd6f4;
}
QPushButton:hover { background-color: #585b70; border-color: #89b4fa; }
QPushButton:pressed { background-color: #313244; }
QPushButton:disabled { color: #6c7086; background-color: #2a2a3c; }
QPushButton#primaryBtn { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; border: none; }
QPushButton#primaryBtn:hover { background-color: #b4befe; }
QPushButton#primaryBtn:disabled { background-color: #45475a; color: #6c7086; }
QPushButton#dangerBtn { background-color: #f38ba8; color: #1e1e2e; }
QPushButton#dangerBtn:hover { background-color: #eba0ac; }

QComboBox QAbstractItemView { background-color: #313244; selection-background-color: #89b4fa; color: #cdd6f4; border: 1px solid #45475a; }

QListWidget {
    background-color: #181825; border: 1px solid #313244; border-radius: 6px;
}
QListWidget::item { border-radius: 4px; padding: 2px; }
QListWidget::item:selected { background-color: #313244; }

QScrollBar:vertical { background: #181825; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 6px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #181825; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: #45475a; border-radius: 6px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #585b70; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QSplitter::handle { background-color: #313244; }
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }

QStatusBar { background-color: #181825; border-top: 1px solid #313244; }
QProgressBar { background-color: #313244; border: 1px solid #45475a; border-radius: 6px; text-align: center; height: 16px; }
QProgressBar::chunk { background-color: #89b4fa; border-radius: 5px; }
QMenu { background-color: #313244; border: 1px solid #45475a; }
QMenu::item:selected { background-color: #45475a; }
QToolTip { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }
QFrame#dropFrame { border: 2px dashed #45475a; border-radius: 8px; background-color: #181825; }
QFrame#dropFrame[dragOver="true"] { border-color: #89b4fa; background-color: #1e1e2e; }
"""


# ===========================================================================
# 工作线程：生成图片
# ===========================================================================

class GenerateWorker(QThread):
    """后台调用 API 生成图片。支持可选的「先 LLM 优化提示词」阶段。"""
    progress = Signal(str)
    prompt_optimized = Signal(str, str)  # (原始提示词, 优化后提示词)
    finished_ok = Signal(list)           # list[GeneratedImage]
    failed = Signal(str)

    def __init__(self, client: AgnesClient, req: GenerateRequest,
                 optimize: bool = False):
        super().__init__()
        self.client = client
        self.req = req
        self.optimize = optimize

    def run(self):
        try:
            t0 = time.time()
            # 阶段 1（可选）：调用 LLM 优化提示词
            if self.optimize:
                self.progress.emit("正在用 Agnes 2.0 Flash 优化提示词…")
                original = self.req.prompt
                try:
                    optimized = self.client.optimize_prompt(original)
                except AgnesAPIError as e:
                    # 优化失败不阻断，回退用原提示词
                    self.progress.emit(f"提示词优化失败，使用原始提示词：{e}")
                    optimized = original
                if optimized and optimized != original:
                    self.req.prompt = optimized
                    self.prompt_optimized.emit(original, optimized)
                    self.progress.emit("提示词优化完成，开始生成图片…")
                else:
                    self.progress.emit("提示词无需优化，开始生成图片…")
            # 阶段 2：调用画图模型
            self.progress.emit("正在生成图片…")
            results = self.client.generate(self.req)
            self.progress.emit(f"完成，耗时 {time.time()-t0:.1f}s，共 {len(results)} 张")
            self.finished_ok.emit(results)
        except AgnesAPIError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"未预期的错误：{e}\n{traceback.format_exc()[-400:]}")


# ===========================================================================
# 可缩放/平移的图片预览
# ===========================================================================

class ImagePreviewView(QWidget):
    """支持滚轮缩放、拖拽平移、双击自适应的图片预览控件。"""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#11111b"))
        self.setPalette(pal)

        self._pixmap: QPixmap | None = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._dragging = False
        self._drag_start = QPoint()
        self._offset_start = QPointF(0, 0)

    def set_image(self, pixmap: QPixmap | None):
        self._pixmap = pixmap
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        if pixmap is not None:
            self.fit_to_window()
        self.update()

    def fit_to_window(self):
        """自适应缩放到控件大小。"""
        if not self._pixmap or self._pixmap.isNull():
            return
        sw = max(self.width() - 20, 1) / self._pixmap.width()
        sh = max(self.height() - 20, 1) / self._pixmap.height()
        self._scale = min(sw, sh, 1.0) if min(sw, sh) < 1.0 else min(sw, sh)
        self._offset = QPointF(0, 0)
        self.update()

    def actual_size(self):
        if not self._pixmap:
            return
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self.update()

    # 事件 ----
    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor("#11111b"))
        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor("#6c7086"))
            painter.setFont(QFont("Microsoft YaHei UI", 12))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "生成的图片将显示在此\n\n滚轮缩放 · 拖拽平移 · 双击自适应")
            return
        # 居中 + 缩放 + 偏移
        pw = self._pixmap.width() * self._scale
        ph = self._pixmap.height() * self._scale
        x = (self.width() - pw) / 2 + self._offset.x()
        y = (self.height() - ph) / 2 + self._offset.y()
        painter.drawPixmap(QRectF(x, y, pw, ph), self._pixmap,
                           QRectF(0, 0, self._pixmap.width(), self._pixmap.height()))
        # 缩放比例提示
        painter.setPen(QColor("#6c7086"))
        painter.setFont(QFont("Consolas", 9))
        painter.drawText(8, self.height() - 10, f"{self._scale*100:.0f}%")

    def wheelEvent(self, e: QWheelEvent):
        if not self._pixmap:
            return
        delta = e.angleDelta().y() / 120
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_scale = self._scale * factor
        new_scale = max(0.05, min(8.0, new_scale))
        # 以鼠标为中心缩放
        mp = e.position() - QPointF(self.width(), self.height()) / 2
        self._offset = (self._offset - mp) * (new_scale / self._scale) + mp
        self._scale = new_scale
        self.update()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton and self._pixmap:
            self._dragging = True
            self._drag_start = e.position().toPoint()
            self._offset_start = QPointF(self._offset)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._dragging:
            delta = e.position().toPoint() - self._drag_start
            self._offset = self._offset_start + QPointF(delta)
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, _):
        self.fit_to_window()

    def resizeEvent(self, _):
        self.update()


# ===========================================================================
# 参考图拖拽区
# ===========================================================================

class ReferenceImageDrop(QFrame):
    """图生图参考图拖拽/选择区。"""

    imageChanged = Signal(object)  # bytes | None

    def __init__(self):
        super().__init__()
        self.setObjectName("dropFrame")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setMaximumHeight(140)

        self._bytes: bytes | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.label = QLabel("拖拽图片到此处，或点击选择\n支持 img2img / 生成变体")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #6c7086; font-size: 11px;")
        layout.addWidget(self.label)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setScaledContents(False)
        self.preview.hide()
        layout.addWidget(self.preview)

        btn_row = QHBoxLayout()
        self.browse_btn = QPushButton(qta.icon("fa5s.folder-open", color="#89b4fa"), " 选择")
        self.browse_btn.setToolTip("选择参考图")
        self.clear_btn = QPushButton(qta.icon("fa5s.times", color="#f38ba8"), " 清除")
        btn_row.addStretch()
        btn_row.addWidget(self.browse_btn)
        btn_row.addWidget(self.clear_btn)
        layout.addLayout(btn_row)

        self.browse_btn.clicked.connect(self._browse)
        self.clear_btn.clicked.connect(self._clear)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择参考图", "", "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            self._bytes = Path(path).read_bytes()
        except Exception as e:
            QMessageBox.warning(self, "读取失败", str(e))
            return
        pix = QPixmap(path)
        self._show_preview(pix, os.path.basename(path))
        self.imageChanged.emit(self._bytes)

    def _show_preview(self, pix: QPixmap, name: str):
        self.label.hide()
        self.preview.show()
        self.preview.setPixmap(pix.scaled(80, 80, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        self.browse_btn.setText(" 更换")
        self.setToolTip(name)

    def _clear(self):
        self._bytes = None
        self.preview.hide()
        self.preview.clear()
        self.label.show()
        self.browse_btn.setText(" 选择")
        self.imageChanged.emit(None)

    # 拖拽
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, _):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, e: QDropEvent):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        md = e.mimeData()
        if md.hasImage():
            img: QImage = md.imageData()
            buf = QBuffer()
            buf.open(QBuffer.ReadWrite)
            img.save(buf, "PNG")
            self._bytes = buf.data().data()
            self._show_preview(QPixmap.fromImage(img), "pasted.png")
            self.imageChanged.emit(self._bytes)
            return
        if md.hasUrls():
            for url in md.urls():
                p = url.toLocalFile()
                if p and Path(p).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                    self._load_file(p)
                    return

    def get_image_bytes(self) -> bytes | None:
        return self._bytes

    def set_image_bytes(self, data: bytes | None):
        if data is None:
            self._clear()
        else:
            self._bytes = data
            pix = QPixmap()
            pix.loadFromData(data)
            self._show_preview(pix, "reference.png")
            self.imageChanged.emit(data)


# ===========================================================================
# 设置对话框
# ===========================================================================

class SettingsDialog(QDialog):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)

        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.timeout_slider = QSlider(Qt.Horizontal)
        self.timeout_slider.setRange(MIN_TIMEOUT, MAX_TIMEOUT)
        self.timeout_slider.setValue(int(config.get("timeout", DEFAULT_TIMEOUT)))
        self.timeout_label = QLabel()
        self.timeout_slider.valueChanged.connect(
            lambda v: self.timeout_label.setText(f"{v} 秒"))
        self.timeout_label.setText(f"{self.timeout_slider.value()} 秒")
        row1 = QHBoxLayout()
        row1.addWidget(self.timeout_slider, 1)
        row1.addWidget(self.timeout_label)
        form.addRow("请求超时（60–360s）", row1)

        self.default_size = QComboBox()
        for name, val in SIZE_PRESETS:
            self.default_size.addItem(name, val)
        cur = config.get("default_size", DEFAULT_SIZE)
        idx = next((i for i in range(self.default_size.count())
                    if self.default_size.itemData(i) == cur), 0)
        self.default_size.setCurrentIndex(idx)
        form.addRow("默认尺寸", self.default_size)

        self.save_key = QCheckBox("自动保存 API Key 到本地配置")
        self.save_key.setChecked(bool(config.get("save_key", True)))
        form.addRow("", self.save_key)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def apply_to_config(self):
        self.config.set("timeout", self.timeout_slider.value())
        self.config.set("default_size", self.default_size.currentData())
        self.config.set("save_key", self.save_key.isChecked())


# ===========================================================================
# 历史画廊缩略图列表
# ===========================================================================

class HistoryGallery(QListWidget):
    """历史画廊：缩略图 + 右键菜单（复用参数/变体/收藏/删除/另存）。"""

    reuseRequested = Signal(object)      # HistoryItem
    variationRequested = Signal(object)  # HistoryItem
    viewRequested = Signal(object)       # HistoryItem
    favoriteToggled = Signal(object)     # HistoryItem
    deleted = Signal(int)                # item_id

    THUMB_W = 150

    def __init__(self, store: HistoryStore):
        super().__init__()
        self.store = store
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(self.THUMB_W, self.THUMB_W))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._on_context)

    def refresh(self, items: list[HistoryItem]):
        self.clear()
        for it in items:
            pix = QPixmap(str(self.store.thumb_fullpath(it)))
            if pix.isNull():
                pix = QPixmap(self.THUMB_W, self.THUMB_W)
                pix.fill(QColor("#313244"))
            # 缩放到正方形并居中
            square = QPixmap(self.THUMB_W, self.THUMB_W)
            square.fill(QColor("#11111b"))
            p = QPainter(square)
            scaled = pix.scaled(self.THUMB_W, self.THUMB_W, Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
            p.drawPixmap((self.THUMB_W - scaled.width()) // 2,
                         (self.THUMB_W - scaled.height()) // 2, scaled)
            # 收藏标记
            if it.favorite:
                p.drawText(QRectF(self.THUMB_W - 20, 2, 18, 16), Qt.AlignCenter, "★")
            p.end()

            li = QListWidgetItem(QIcon(square), "")
            li.setData(Qt.UserRole, it)
            mode_tag = {"txt2img": "文生图", "img2img": "图生图", "variation": "变体"}.get(it.mode, it.mode)
            li.setToolTip(
                f"{it.prompt[:60]}\n"
                f"━━━━━━━━━━\n"
                f"模式: {mode_tag}\n尺寸: {it.size}\n"
                f"{it.width}×{it.height} {it.fmt}\n"
                f"时间: {datetime.fromtimestamp(it.created_at):%Y-%m-%d %H:%M}\n"
                f"{'★ 已收藏' if it.favorite else '点击右键收藏'}")
            li.setSizeHint(QSize(self.THUMB_W + 8, self.THUMB_W + 8))
            self.addItem(li)

    def _item_to_history(self, item: QListWidgetItem) -> HistoryItem | None:
        return item.data(Qt.UserRole)

    def _on_double_click(self, item):
        it = self._item_to_history(item)
        if it:
            self.viewRequested.emit(it)

    def _on_context(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return
        it = self._item_to_history(item)
        if not it:
            return
        menu = QMenu(self)
        a_view = menu.addAction(qta.icon("fa5s.search-plus", color="#89b4fa"), "查看大图")
        a_reuse = menu.addAction(qta.icon("fa5s.redo", color="#a6e3a1"), "复用参数")
        a_var = menu.addAction(qta.icon("fa5s.random", color="#f9e2af"), "以此图生成变体")
        menu.addSeparator()
        fav_text = "取消收藏" if it.favorite else "加入收藏"
        a_fav = menu.addAction(qta.icon("fa5s.star", color="#f9e2af"), fav_text)
        a_copy = menu.addAction(qta.icon("fa5s.copy", color="#89b4fa"), "复制提示词")
        a_save = menu.addAction(qta.icon("fa5s.download", color="#89b4fa"), "另存为…")
        a_open = menu.addAction(qta.icon("fa5s.folder-open", color="#89b4fa"), "打开所在文件夹")
        menu.addSeparator()
        a_del = menu.addAction(qta.icon("fa5s.trash", color="#f38ba8"), "删除")

        action = menu.exec(self.mapToGlobal(pos))
        if action == a_view:
            self.viewRequested.emit(it)
        elif action == a_reuse:
            self.reuseRequested.emit(it)
        elif action == a_var:
            self.variationRequested.emit(it)
        elif action == a_fav:
            self.favoriteToggled.emit(it)
        elif action == a_copy:
            QApplication.clipboard().setText(it.prompt)
        elif action == a_save:
            self._save_as(it)
        elif action == a_open:
            self._open_folder(it)
        elif action == a_del:
            self.deleted.emit(it.id)

    def _save_as(self, it: HistoryItem):
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存为", f"{it.prompt[:20]}.png", "PNG 图片 (*.png);;JPEG (*.jpg)")
        if dst:
            try:
                Path(dst).write_bytes(Path(self.store.image_fullpath(it)).read_bytes())
            except Exception as e:
                QMessageBox.warning(self, "保存失败", str(e))

    def _open_folder(self, it: HistoryItem):
        p = self.store.image_fullpath(it)
        os.system(f'explorer /select,"{p}"')


# ===========================================================================
# 主窗口
# ===========================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Agnes Image Studio — 图片生成器")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        self.config = ConfigStore()
        self.store = HistoryStore()
        self.worker: GenerateWorker | None = None

        self._build_ui()
        self._load_settings()
        self._refresh_history()
        self._setup_shortcuts()

        self.status(f"就绪。默认模型：{self.model_combo.currentData()} ｜ 数据目录：{self.store.db_path.parent}")

    # ------------------- UI 构建 -------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 顶栏标题 + 设置
        topbar = QHBoxLayout()
        title = QLabel("✦ Agnes Image Studio")
        title.setObjectName("titleLabel")
        topbar.addWidget(title)
        topbar.addStretch()
        self.fav_only_btn = QPushButton(qta.icon("fa5s.star", color="#f9e2af"), " 仅收藏")
        self.fav_only_btn.setCheckable(True)
        self.fav_only_btn.setToolTip("只显示收藏的图片")
        self.fav_only_btn.toggled.connect(lambda _: self._refresh_history())
        topbar.addWidget(self.fav_only_btn)
        self.settings_btn = QPushButton(qta.icon("fa5s.cog", color="#89b4fa"), " 设置")
        self.settings_btn.clicked.connect(self._open_settings)
        topbar.addWidget(self.settings_btn)
        root.addLayout(topbar)

        # 三栏分割
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 640, 260])
        root.addWidget(splitter, 1)

        # 状态栏
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setRange(0, 0)  # 不定式滚动
        self.progress_bar.hide()
        sb.addPermanentWidget(self.progress_bar)
        self._status_label = QLabel("就绪")
        sb.addWidget(self._status_label, 1)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(8)

        # API Key
        gb_key = QGroupBox("API Key")
        gl = QVBoxLayout(gb_key)
        gl.setContentsMargins(10, 16, 10, 10)
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-...")
        key_row.addWidget(self.key_edit, 1)
        self.key_show_btn = QToolButton()
        self.key_show_btn.setCheckable(True)
        self.key_show_btn.setIcon(qta.icon("fa5s.eye", color="#89b4fa"))
        self.key_show_btn.toggled.connect(self._toggle_key_visible)
        key_row.addWidget(self.key_show_btn)
        gl.addLayout(key_row)
        v.addWidget(gb_key)

        # 模式切换
        gb_mode = QGroupBox("生成模式")
        gm = QHBoxLayout(gb_mode)
        gm.setContentsMargins(10, 16, 10, 10)
        self.mode_txt = QPushButton(qta.icon("fa5s.keyboard", color="#89b4fa"), " 文生图")
        self.mode_img = QPushButton(qta.icon("fa5s.image", color="#89b4fa"), " 图生图")
        for b in (self.mode_txt, self.mode_img):
            b.setCheckable(True)
            gm.addWidget(b)
        self.mode_txt.setChecked(True)
        self.mode_txt.clicked.connect(lambda: self._set_mode("txt2img"))
        self.mode_img.clicked.connect(lambda: self._set_mode("img2img"))
        v.addWidget(gb_mode)

        # 参考图（图生图时显示）
        self.ref_drop = ReferenceImageDrop()
        self.ref_drop.imageChanged.connect(self._on_ref_changed)
        self.ref_drop.hide()
        v.addWidget(self.ref_drop)

        # Prompt
        gb_p = QGroupBox("提示词 Prompt")
        gp = QVBoxLayout(gb_p)
        gp.setContentsMargins(10, 16, 10, 10)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述你想生成的图片…（Ctrl+Enter 生成）")
        self.prompt_edit.setMinimumHeight(90)
        gp.addWidget(self.prompt_edit, 1)

        # 优化提示词开关：勾选后生成前先用 LLM (agnes-2.0-flash) 优化提示词
        opt_row = QHBoxLayout()
        opt_row.setContentsMargins(0, 0, 0, 0)
        self.optimize_chk = QCheckBox("AI 优化提示词")
        self.optimize_chk.setToolTip(
            "勾选后，生成前会先把你的提示词发给 Agnes 2.0 Flash 大模型优化，\n"
            "自动补充构图/光影/风格等细节，再用优化后的提示词生成图片。\n"
            "优化过程会多花几秒，结果会在下方信息栏显示。")
        opt_row.addWidget(self.optimize_chk)
        opt_row.addStretch()
        gp.addLayout(opt_row)

        # 模板：仅记录当前选择，发请求时才在后台与用户提示词合并，不污染输入框
        tpl_row = QHBoxLayout()
        tpl_row.setContentsMargins(0, 0, 0, 0)
        tpl_row.addWidget(QLabel("模板:"))
        self.template_combo = QComboBox()
        self.template_combo.addItem("（不套用模板）", "")
        for name, val in BUILTIN_TEMPLATES:
            self.template_combo.addItem(name, val)
        self.template_combo.setToolTip(
            "选择风格模板后，生成时会自动把风格词拼接到你的提示词末尾，\n"
            "输入框内容不会被改动。选「（不套用模板）」则只用你输入的内容。")
        tpl_row.addWidget(self.template_combo, 1)
        gp.addLayout(tpl_row)

        # 收藏提示词
        fav_row = QHBoxLayout()
        fav_row.setContentsMargins(0, 0, 0, 0)
        self.fav_combo = QComboBox()
        self.fav_combo.addItem("我的收藏提示词…", "")
        self.fav_combo.currentIndexChanged.connect(self._use_fav_prompt)
        fav_row.addWidget(QLabel("收藏:"), 0)
        fav_row.addWidget(self.fav_combo, 1)
        self.add_fav_btn = QPushButton(qta.icon("fa5s.bookmark", color="#f9e2af"), " 收藏当前")
        self.add_fav_btn.clicked.connect(self._add_fav_prompt)
        fav_row.addWidget(self.add_fav_btn)
        gp.addLayout(fav_row)

        v.addWidget(gb_p, 1)

        # 参数
        gb_param = QGroupBox("参数")
        gpa = QGridLayout(gb_param)
        gpa.setContentsMargins(10, 16, 10, 10)
        gpa.setHorizontalSpacing(8)
        gpa.setVerticalSpacing(8)
        gpa.addWidget(QLabel("模型:"), 0, 0)
        self.model_combo = QComboBox()
        for model_id, model_name in MODELS:
            self.model_combo.addItem(model_name, model_id)
        self.model_combo.setCurrentIndex(0)
        self.model_combo.setToolTip("选择生成模型\n2.1 Flash：质量更高（推荐）\n2.0 Flash：速度更快")
        gpa.addWidget(self.model_combo, 0, 1)
        gpa.addWidget(QLabel("尺寸:"), 1, 0)
        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        for name, val in SIZE_PRESETS:
            self.size_combo.addItem(f"{name}  ({val})", val)
        self.size_combo.setCurrentIndex(0)
        gpa.addWidget(self.size_combo, 1, 1)
        gpa.addWidget(QLabel("张数:"), 2, 0)
        self.n_spin = QSpinBox()
        self.n_spin.setRange(1, 4)
        self.n_spin.setValue(1)
        self.n_spin.setToolTip("一次生成 1–4 张")
        gpa.addWidget(self.n_spin, 2, 1)
        v.addWidget(gb_param)

        # 生成按钮
        self.gen_btn = QPushButton(qta.icon("fa5s.magic", color="#1e1e2e"), "  生成图片")
        self.gen_btn.setObjectName("primaryBtn")
        self.gen_btn.setMinimumHeight(40)
        self.gen_btn.clicked.connect(self._on_generate)
        v.addWidget(self.gen_btn)

        self.cur_mode = "txt2img"
        self.cur_ref_bytes: bytes | None = None
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        # 工具栏
        bar = QHBoxLayout()
        bar.addWidget(QLabel("预览"))
        bar.addStretch()
        self.fit_btn = QPushButton(qta.icon("fa5s.expand", color="#89b4fa"), " 自适应")
        self.fit_btn.clicked.connect(lambda: self.preview.fit_to_window())
        self.actual_btn = QPushButton(qta.icon("fa5s.search", color="#89b4fa"), " 1:1")
        self.actual_btn.clicked.connect(lambda: self.preview.actual_size())
        self.copy_btn = QPushButton(qta.icon("fa5s.copy", color="#a6e3a1"), " 复制图片")
        self.copy_btn.clicked.connect(self._copy_current_image)
        self.save_btn = QPushButton(qta.icon("fa5s.download", color="#89b4fa"), " 另存为")
        self.save_btn.clicked.connect(self._save_current_as)
        for b in (self.fit_btn, self.actual_btn, self.copy_btn, self.save_btn):
            bar.addWidget(b)
        v.addLayout(bar)

        self.preview = ImagePreviewView()
        v.addWidget(self.preview, 1)

        # 多图结果切换（批量生成时）
        self.multi_bar = QWidget()
        mb = QHBoxLayout(self.multi_bar)
        mb.setContentsMargins(0, 0, 0, 0)
        mb.addWidget(QLabel("本次结果:"))
        self.multi_combo = QComboBox()
        self.multi_combo.currentIndexChanged.connect(self._switch_result)
        mb.addWidget(self.multi_combo, 1)
        self.multi_bar.hide()
        v.addWidget(self.multi_bar)

        # revised prompt 信息
        self.info_label = QLabel("")
        self.info_label.setObjectName("infoLabel")
        self.info_label.setWordWrap(True)
        self.info_label.setFrameShape(QFrame.StyledPanel)
        self.info_label.setStyleSheet("padding:6px;")
        v.addWidget(self.info_label)

        self._current_results: list[GeneratedImage] = []
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        h = QHBoxLayout()
        h.addWidget(QLabel("历史画廊"))
        h.addStretch()
        self.history_count = QLabel("0")
        self.history_count.setObjectName("infoLabel")
        h.addWidget(self.history_count)
        v.addLayout(h)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索提示词…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh_history)
        v.addWidget(self.search_edit)

        self.gallery = HistoryGallery(self.store)
        self.gallery.viewRequested.connect(self._view_history)
        self.gallery.reuseRequested.connect(self._reuse_history)
        self.gallery.variationRequested.connect(self._variation_from_history)
        self.gallery.favoriteToggled.connect(self._toggle_fav)
        self.gallery.deleted.connect(self._delete_history)
        v.addWidget(self.gallery, 1)
        return panel

    # ------------------- 设置与初始化 -------------------
    def _load_settings(self):
        if self.config.get("save_key", True):
            key = self.config.get("api_key", "")
            if key:
                self.key_edit.setText(key)
        # 默认尺寸
        ds = self.config.get("default_size", DEFAULT_SIZE)
        for i in range(self.size_combo.count()):
            if self.size_combo.itemData(i) == ds:
                self.size_combo.setCurrentIndex(i)
                break
        self._reload_fav_prompts()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_generate)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._on_generate)

    def _toggle_key_visible(self, checked):
        self.key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.key_show_btn.setIcon(qta.icon(
            "fa5s.eye-slash" if checked else "fa5s.eye", color="#89b4fa"))

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            dlg.apply_to_config()

    # ------------------- 模式切换 -------------------
    def _set_mode(self, mode: str):
        self.cur_mode = mode
        if mode == "img2img":
            self.mode_txt.setChecked(False)
            self.mode_img.setChecked(True)
            self.ref_drop.show()
        else:
            self.mode_txt.setChecked(True)
            self.mode_img.setChecked(False)
            self.ref_drop.hide()

    def _on_ref_changed(self, data):
        self.cur_ref_bytes = data

    # ------------------- 模板与收藏 -------------------
    def _build_prompt(self) -> str:
        """返回真正发给 API 的提示词 = 用户输入 + 当前模板风格词（若有）。

        模板词不写入输入框，只在发请求时合并，保持输入框干净。
        """
        user_text = self.prompt_edit.toPlainText().strip()
        snippet = self.template_combo.currentData() or ""
        snippet = snippet.strip()
        if not snippet:
            return user_text
        if not user_text:
            return snippet
        return f"{user_text}, {snippet}"

    def _reload_fav_prompts(self):
        favs = self.config.get("fav_prompts", []) or []
        self.fav_combo.clear()
        self.fav_combo.addItem("我的收藏提示词…", "")
        for fp in favs:
            self.fav_combo.addItem(fp[:40], fp)

    def _use_fav_prompt(self, idx):
        if idx <= 0:
            return
        text = self.fav_combo.itemData(idx)
        if text:
            self.prompt_edit.setPlainText(text)
        QTimer.singleShot(0, lambda: self.fav_combo.setCurrentIndex(0))

    def _add_fav_prompt(self):
        text = self.prompt_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "提示词为空，无法收藏。")
            return
        favs = self.config.get("fav_prompts", []) or []
        if text in favs:
            QMessageBox.information(self, "提示", "该提示词已收藏。")
            return
        favs.append(text)
        self.config.set("fav_prompts", favs)
        self._reload_fav_prompts()
        self.status("已收藏当前提示词")

    # ------------------- 生成 -------------------
    def _get_size(self) -> str:
        data = self.size_combo.currentData()
        return data or self.size_combo.currentText().strip() or DEFAULT_SIZE

    def _on_generate(self):
        api_key = self.key_edit.text().strip()
        user_prompt = self.prompt_edit.toPlainText().strip()
        if not api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先在左上角输入 Agnes API Key。")
            return
        if not user_prompt:
            QMessageBox.warning(self, "缺少提示词", "请输入提示词 Prompt。")
            return
        if self.cur_mode in ("img2img", "variation") and not self.cur_ref_bytes:
            QMessageBox.warning(self, "缺少参考图", "图生图模式下请先拖入或选择一张参考图。")
            return

        # 发请求时才把模板风格词与用户提示词合并（输入框内容不被改动）
        final_prompt = self._build_prompt()

        # 保存 key（按设置）
        if self.config.get("save_key", True):
            self.config.set("api_key", api_key)

        size = self._get_size()
        try:
            req = GenerateRequest(
                prompt=final_prompt, api_key=api_key, size=size, n=self.n_spin.value(),
                mode=self.cur_mode,
                model=self.model_combo.currentData() or MODEL,
                reference_images=[self._save_temp_ref()] if self.cur_ref_bytes and self.cur_mode == "img2img" else [],
                timeout=self.config.get("timeout", DEFAULT_TIMEOUT),
            )
        except ValueError as e:
            QMessageBox.warning(self, "参数错误", str(e))
            return

        # 启动后台线程
        self._set_generating(True)
        self._optimized_prompt = None  # 重置，由 worker 在优化成功后回填
        self.client = AgnesClient(api_key, timeout=req.timeout)
        self.worker = GenerateWorker(self.client, req, optimize=self.optimize_chk.isChecked())
        self.worker.progress.connect(self.status)
        self.worker.prompt_optimized.connect(self._on_prompt_optimized)
        self.worker.finished_ok.connect(self._on_results)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_prompt_optimized(self, original: str, optimized: str):
        """LLM 优化完成后，在信息栏展示对比，便于用户了解优化了什么。"""
        self._optimized_prompt = optimized
        self.info_label.setText(
            f"✨ 提示词已由 AI 优化：\n"
            f"原：{original}\n"
            f"优化：{optimized}")

    def _save_temp_ref(self) -> str:
        """把当前参考图 bytes 存成临时文件，供 client 转 data URI。"""
        import tempfile
        path = Path(tempfile.gettempdir()) / f"agnes_ref_{int(time.time()*1000)}.png"
        path.write_bytes(self.cur_ref_bytes)
        return str(path)

    def _set_generating(self, on: bool):
        self.gen_btn.setEnabled(not on)
        self.gen_btn.setText("  生成中…" if on else "  生成图片")
        self.progress_bar.setVisible(on)
        if on:
            self.status("正在生成…")

    def _on_results(self, results: list[GeneratedImage]):
        self._set_generating(False)
        if not results:
            self.status("未返回图片")
            return
        self._current_results = results
        # 多图切换栏
        if len(results) > 1:
            self.multi_combo.blockSignals(True)
            self.multi_combo.clear()
            for i, r in enumerate(results):
                self.multi_combo.addItem(f"第 {i+1} 张 ({r.width}×{r.height})", i)
            self.multi_combo.blockSignals(False)
            self.multi_bar.show()
        else:
            self.multi_bar.hide()
        self._show_result(0)

        # 写入历史（记录实际发给画图 API 的提示词；若经过 AI 优化则存优化后的）
        actual_prompt = getattr(self, "_optimized_prompt", None) or self._build_prompt()
        user_prompt = self.prompt_edit.toPlainText().strip()
        for r in results:
            try:
                self.store.add(
                    prompt=actual_prompt,
                    mode=self.cur_mode, size=self._get_size(),
                    image_bytes=r.image_bytes,
                    revised_prompt=r.revised_prompt, url=r.url,
                    reference_image=None,
                    params={"n": len(results), "source": r.source_kind,
                            "model": self.model_combo.currentData() or MODEL,
                            "optimized": getattr(self, "_optimized_prompt", None) is not None,
                            "original_prompt": user_prompt},
                )
            except Exception as e:
                print("写入历史失败:", e)
        self._refresh_history()
        self.status(f"生成完成，共 {len(results)} 张，已存入历史画廊")

    def _show_result(self, idx: int):
        if not self._current_results or idx >= len(self._current_results):
            return
        r = self._current_results[idx]
        img = QImage.fromData(r.image_bytes)
        pix = QPixmap.fromImage(img)
        self.preview.set_image(pix)
        info_parts = [f"{r.width}×{r.height} {r.fmt}", f"{r.size_kb:.1f} KB"]
        if r.url:
            info_parts.append("url ✓")
        info = "  |  ".join(info_parts)
        if r.revised_prompt:
            info += f"\n优化后的提示词: {r.revised_prompt}"
        self.info_label.setText(info)

    def _switch_result(self, idx):
        if idx >= 0:
            self._show_result(idx)

    def _on_failed(self, msg: str):
        self._set_generating(False)
        self.status("生成失败")
        QMessageBox.critical(self, "生成失败", msg)

    # ------------------- 预览操作 -------------------
    def _copy_current_image(self):
        if not self._current_results:
            return
        r = self._current_results[max(self.multi_combo.currentIndex(), 0)]
        img = QImage.fromData(r.image_bytes)
        QApplication.clipboard().setImage(img)
        self.status("已复制到剪贴板")

    def _save_current_as(self):
        if not self._current_results:
            return
        idx = max(self.multi_combo.currentIndex(), 0) if self.multi_bar.isVisible() else 0
        r = self._current_results[idx]
        name = self.prompt_edit.toPlainText().strip()[:20] or "agnes"
        dst, _ = QFileDialog.getSaveFileName(
            self, "另存为", f"{name}.png", "PNG 图片 (*.png);;JPEG (*.jpg);;WebP (*.webp)")
        if dst:
            try:
                Path(dst).write_bytes(r.image_bytes)
                self.status(f"已保存：{dst}")
            except Exception as e:
                QMessageBox.warning(self, "保存失败", str(e))

    # ------------------- 历史画廊 -------------------
    def _refresh_history(self):
        kw = self.search_edit.text().strip() if hasattr(self, "search_edit") else ""
        fav_only = self.fav_only_btn.isChecked() if hasattr(self, "fav_only_btn") else False
        if kw:
            items = self.store.search(kw)
        elif fav_only:
            items = self.store.list_all(favorites_only=True)
        else:
            items = self.store.list_all()
        self.gallery.refresh(items)
        self.history_count.setText(f"{len(items)} 张")

    def _view_history(self, it: HistoryItem):
        pix = QPixmap(str(self.store.image_fullpath(it)))
        self.preview.set_image(pix)
        mode = {"txt2img": "文生图", "img2img": "图生图", "variation": "变体"}.get(it.mode, it.mode)
        self.info_label.setText(
            f"{it.width}×{it.height} {it.fmt}  |  {mode}  |  {it.size}\n"
            f"提示词: {it.prompt}" + (f"\n优化: {it.revised_prompt}" if it.revised_prompt else ""))
        self.status(f"查看历史图片 (id={it.id})")

    def _reuse_history(self, it: HistoryItem):
        self.prompt_edit.setPlainText(it.prompt)
        # 尺寸
        for i in range(self.size_combo.count()):
            if self.size_combo.itemData(i) == it.size:
                self.size_combo.setCurrentIndex(i)
                break
        else:
            self.size_combo.setEditText(it.size)
        self._set_mode("txt2img")
        self.status("已复用历史参数，点击「生成图片」即可重新生成")

    def _variation_from_history(self, it: HistoryItem):
        """以历史图为参考图，生成变体。"""
        try:
            ref_bytes = Path(self.store.image_fullpath(it)).read_bytes()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取参考图失败：{e}")
            return
        self._set_mode("img2img")
        self.ref_drop.set_image_bytes(ref_bytes)
        self.cur_ref_bytes = ref_bytes
        self.prompt_edit.setPlainText(
            f"create a variation of this image, {it.prompt}" if it.prompt else "create a creative variation of this image")
        self.status("已载入参考图，可修改提示词后点击「生成图片」生成变体")

    def _toggle_fav(self, it: HistoryItem):
        self.store.set_favorite(it.id, not it.favorite)
        self._refresh_history()

    def _delete_history(self, item_id: int):
        reply = QMessageBox.question(
            self, "删除确认", "确定删除这张图片吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.store.delete(item_id)
            self._refresh_history()
            self.status(f"已删除 (id={item_id})")

    # ------------------- 杂项 -------------------
    def status(self, msg: str):
        self._status_label.setText(msg)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "正在生成", "图片正在生成中，确定退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                e.ignore()
                return
            self.worker.terminate()
        self.store.close()
        e.accept()


# ===========================================================================
# 入口
# ===========================================================================

def main():
    # 高 DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Agnes Image Studio")
    app.setWindowIcon(qta.icon("fa5s.images", color="#89b4fa"))
    app.setStyleSheet(DARK_QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
