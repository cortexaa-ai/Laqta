# -*- coding: utf-8 -*-
"""
لقطة (Laqta) — محرر سكرين شوت بيشتغل بالخلفية على Windows.

- بتصوّر بـ Win+Shift+S (أداة Windows العادية)
- المحرر بيفتح لحاله بالصورة
- كل تعديل بيتنسخ للحافظة تلقائياً وبينحفظ كملف
- Ctrl+V بأي مكان
"""
import ctypes
import datetime
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import (QByteArray, QBuffer, QIODevice, QLineF, QMimeData, QStandardPaths,
                            QObject, QPointF, QRectF, QSize, Qt, QTimer)
from PySide6.QtGui import (QAbstractTextDocumentLayout, QAction, QActionGroup,
                           QBrush, QColor, QFont, QFontMetricsF, QIcon, QImage,
                           QKeySequence, QPainter, QPainterPath,
                           QPainterPathStroker, QPalette, QPen, QPixmap,
                           QPolygonF, QTextCursor, QUndoCommand, QUndoStack)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox,
                               QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGraphicsDropShadowEffect, QGraphicsItem,
                               QGraphicsScene, QGraphicsTextItem, QGraphicsView,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QSlider, QSpinBox, QStyle,
                               QStyleOptionGraphicsItem, QSystemTrayIcon,
                               QTabWidget, QToolBar, QToolButton, QVBoxLayout,
                               QWidget, QWidgetAction)

APP_NAME = "Laqta"
APP_TITLE = "لقطة"
IS_WIN = sys.platform == "win32"
OWN_MIME = "application/x-laqta"
APP_DIR = Path(os.getenv("APPDATA") or Path.home() / ".config") / APP_NAME
CFG_FILE = APP_DIR / "settings.json"

DEFAULTS = {
    "trigger": "shortcut",          # shortcut = بس بعد Win+Shift+S | any = أي صورة تنسخ
    "also_printscreen": True,
    "open_editor": True,
    "start_with_windows": True,
    "notify": True,
    "auto_copy": True,
    "auto_save": True,
    "save_dir": "",  # فاضي = فولدر Pictures الحقيقي (حتى لو على OneDrive)
    "name_pattern": "Laqta_%Y-%m-%d_%H-%M-%S",
    "format": "png",
    "jpg_quality": 92,
    "maximized": True,
    "always_on_top": False,
    "enter_closes": True,
    "fit_on_open": True,
    "color": "#e53935",
    "fill": "#00000000",
    "width": 4,
    "font_size": 28,
    "shadow": True,
    "strength": 12,
    "spot_dim": 150,
    "emoji": "😀",
    "last_tool": "rect",
}

PALETTE = ["#e53935", "#fb8c00", "#fdd835", "#43a047", "#00acc1",
           "#1e88e5", "#8e24aa", "#ffffff", "#9e9e9e", "#111111"]

EMOJIS = ["😀", "😂", "😍", "🤔", "😎", "😭", "😡", "😱", "🥳", "🙄",
          "👍", "👎", "👏", "🙏", "💪", "👀", "👉", "👈", "👆", "👇",
          "✅", "❌", "⚠️", "❓", "❗", "💡", "⭐", "❤️", "🔥", "🎉",
          "🚀", "📌", "📎", "🔒", "🔑", "🐞", "🛠️", "💬", "💯", "🆕"]

TOOLS = [
    # id, glyph, name, key
    ("select", "🖱", "تحديد وتحريك", "V"),
    ("rect", "▭", "مستطيل", "R"),
    ("ellipse", "◯", "دائرة", "E"),
    ("line", "╱", "خط", "L"),
    ("arrow", "➚", "سهم", "A"),
    ("pen", "✎", "قلم حر", "P"),
    ("highlight", "🖍", "هايلايتر", "H"),
    ("text", "T", "نص", "T"),
    ("balloon", "💬", "فقاعة كلام", "B"),
    ("step", "①", "ترقيم خطوات", "N"),
    ("emoji", "😀", "ستيكر إيموجي", "J"),
    ("blur", "💧", "تغبيش", "X"),
    ("pixel", "▦", "بكسلة", "Q"),
    ("spot", "🔦", "سبوتلايت", "F"),
    ("crop", "✂", "قص", "C"),
]
TOOL_KEYS = {k: t for t, _, _, k in TOOLS}


# ───────────────────────────── helpers ─────────────────────────────

def try_dir(d):
    try:
        d = Path(d)
        d.mkdir(parents=True, exist_ok=True)
        return d if d.is_dir() else None
    except Exception:
        return None


def default_save_dirs():
    out = []
    pics = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)  # بيعرف OneDrive
    if pics:
        out.append(Path(pics) / "Laqta")
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    if docs:
        out.append(Path(docs) / "Laqta")
    out.append(APP_DIR / "Screenshots")
    return out


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            self.update(json.loads(CFG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
        self.fix_save_dir()

    def fix_save_dir(self):
        """لو الفولدر مش موجود أو ما بينعمل، اختار أول فولدر شغّال."""
        for cand in ([self.get("save_dir")] if self.get("save_dir") else []) + default_save_dirs():
            d = try_dir(cand)
            if d:
                self["save_dir"] = str(d)
                return
        self["save_dir"] = str(Path.cwd())

    def save(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            CFG_FILE.write_text(json.dumps(self, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def contrast(c):
    c = QColor(c)
    return QColor("#111") if (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) > 150 else QColor("#fff")


def swatch_icon(color, size=18):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    if c.alpha() < 255:  # checker for transparency
        for y in range(0, size, 6):
            for x in range(0, size, 6):
                p.fillRect(x, y, 6, 6, QColor("#bbb") if (x + y) // 6 % 2 else QColor("#eee"))
    if c.alpha() == 0:
        p.setPen(QPen(QColor("#e53935"), 2))
        p.drawLine(2, size - 2, size - 2, 2)
    else:
        p.fillRect(0, 0, size, size, c)
    p.setPen(QPen(QColor("#666"), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 3, 3)
    p.end()
    return QIcon(pm)


def app_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#6c5ce7"))
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    pen = QPen(QColor("white"), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    for (x, y, dx, dy) in [(14, 14, 1, 1), (50, 14, -1, 1), (14, 50, 1, -1), (50, 50, -1, -1)]:
        p.drawLine(QPointF(x, y), QPointF(x + 11 * dx, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + 11 * dy))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffd166"))
    p.drawEllipse(QPointF(32, 32), 7, 7)
    p.end()
    return QIcon(pm)


def set_shadow(item, on):
    if on:
        eff = QGraphicsDropShadowEffect()
        eff.setBlurRadius(10)
        eff.setOffset(2, 3)
        eff.setColor(QColor(0, 0, 0, 150))
        item.setGraphicsEffect(eff)
    else:
        item.setGraphicsEffect(None)


def set_startup(enabled):
    if not IS_WIN:
        return
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if enabled:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"'
            else:
                pyw = Path(sys.executable).with_name("pythonw.exe")
                exe = pyw if pyw.exists() else Path(sys.executable)
                cmd = f'"{exe}" "{Path(__file__).resolve()}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def force_foreground(hwnd, keep_top=False):
    """Windows ما بيسمح لبرنامج بالخلفية يطلع قدام بسهولة — هاي الحيلة."""
    if not IS_WIN:
        return
    try:
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        fg = u.GetForegroundWindow()
        t_fg = u.GetWindowThreadProcessId(fg, None)
        t_me = k.GetCurrentThreadId()
        u.AttachThreadInput(t_fg, t_me, True)
        HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
        flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW
        u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        if not keep_top:
            u.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        u.SetForegroundWindow(hwnd)
        u.BringWindowToTop(hwnd)
        u.AttachThreadInput(t_fg, t_me, False)
    except Exception:
        pass


def draw_doc(painter, text_item):
    """يرسم نص بدون مؤشر الكتابة (للتصدير)."""
    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.palette.setColor(QPalette.Text, text_item.defaultTextColor())
    text_item.document().documentLayout().draw(painter, ctx)


def img_digest(img):
    small = img.scaled(48, 48, Qt.IgnoreAspectRatio, Qt.FastTransformation).convertToFormat(QImage.Format_RGB32)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    small.save(buf, "BMP")
    return hashlib.md5(bytes(ba)).hexdigest() + f"{img.width()}x{img.height()}"


# ───────────────────────────── annotation items ─────────────────────────────

class Anno(QGraphicsItem):
    shadow_ok = True

    def __init__(self, ed, props):
        super().__init__()
        self.ed = ed
        self.props = dict(props)
        self._added = False
        self._h = None
        self._lod = 1.0
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable)
        self.setAcceptHoverEvents(True)
        self.setZValue(ed.next_z())
        set_shadow(self, self.shadow_ok and self.props.get("shadow"))

    # --- props / geometry API ---
    def set_prop(self, k, v):
        self.prepareGeometryChange()
        self.props[k] = v
        if k == "shadow":
            set_shadow(self, self.shadow_ok and v)
        self.on_props()
        self.update()

    def on_props(self):
        pass

    def geom(self):
        return None

    def set_geom(self, g):
        pass

    def handles(self):
        return []

    def move_handle(self, i, p, mods):
        pass

    def update_drag(self, p0, p1, mods):
        pass

    def is_valid(self):
        return True

    def creating_done(self):
        pass

    def pad(self):
        return self.props.get("width", 4) / 2 + 12

    def core_rect(self):
        return QRectF()

    def body_path(self):
        p = QPainterPath()
        p.addRect(self.core_rect())
        return p

    # --- Qt ---
    def boundingRect(self):
        d = self.pad()
        return self.core_rect().adjusted(-d, -d, d, d)

    def shape(self):
        p = QPainterPath(self.body_path())
        p.setFillRule(Qt.WindingFill)
        if self.isSelected():
            s = 9 / self._lod
            for h in self.handles():
                p.addRect(QRectF(h.x() - s, h.y() - s, 2 * s, 2 * s))
        return p

    def paint(self, painter, opt, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        self._lod = max(0.05, QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform()))
        self.draw(painter)
        if self.isSelected() and not self.ed.exporting:
            self.draw_selection(painter)

    def draw(self, p):
        pass

    def draw_selection(self, p):
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 150, 255), 1 / self._lod, Qt.DashLine))
        p.drawRect(self.core_rect())
        s = 5 / self._lod
        p.setPen(QPen(QColor(0, 120, 215), 1.5 / self._lod))
        p.setBrush(QColor("white"))
        for h in self.handles():
            p.drawEllipse(h, s, s)
        p.restore()

    def hit_handle(self, pos):
        s = 9 / self._lod
        for i, h in enumerate(self.handles()):
            if abs(h.x() - pos.x()) <= s and abs(h.y() - pos.y()) <= s:
                return i
        return None

    def hoverMoveEvent(self, e):
        if self.isSelected() and self.hit_handle(e.pos()) is not None:
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(e)

    def mousePressEvent(self, e):
        if self.isSelected() and e.button() == Qt.LeftButton:
            i = self.hit_handle(e.pos())
            if i is not None:
                self._h = i
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._h is not None:
            self.prepareGeometryChange()
            self.move_handle(self._h, e.pos(), e.modifiers())
            self.update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._h is not None:
            self._h = None
            e.accept()
            return
        super().mouseReleaseEvent(e)


def snap_square(p0, p1, mods):
    if mods & Qt.ShiftModifier:
        dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
        d = max(abs(dx), abs(dy))
        return QPointF(p0.x() + math.copysign(d, dx or 1), p0.y() + math.copysign(d, dy or 1))
    return p1


class RectAnno(Anno):
    def __init__(self, ed, props):
        super().__init__(ed, props)
        self.r = QRectF()

    def core_rect(self):
        return self.r

    def update_drag(self, p0, p1, mods):
        self.prepareGeometryChange()
        self.r = QRectF(p0, snap_square(p0, p1, mods)).normalized()
        self.on_geom()
        self.update()

    def on_geom(self):
        pass

    def is_valid(self):
        return self.r.width() > 3 and self.r.height() > 3

    def geom(self):
        return QRectF(self.r)

    def set_geom(self, g):
        self.prepareGeometryChange()
        self.r = QRectF(g)
        self.on_geom()
        self.update()

    def handles(self):
        r = self.r
        return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]

    def move_handle(self, i, p, mods):
        r = QRectF(self.r)
        [r.setTopLeft, r.setTopRight, r.setBottomRight, r.setBottomLeft][i](p)
        self.r = r.normalized()
        self.on_geom()

    def pen(self):
        return QPen(QColor(self.props["color"]), self.props["width"], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    def draw(self, p):
        p.setPen(self.pen())
        p.setBrush(QColor(self.props["fill"]))
        p.drawRoundedRect(self.r, 3, 3)


class EllipseAnno(RectAnno):
    def body_path(self):
        p = QPainterPath()
        p.addEllipse(self.r)
        return p

    def draw(self, p):
        p.setPen(self.pen())
        p.setBrush(QColor(self.props["fill"]))
        p.drawEllipse(self.r)


class BlurAnno(RectAnno):
    shadow_ok = False

    def __init__(self, ed, props, mode="blur"):
        super().__init__(ed, props)
        self.mode = mode
        self._key = None
        self._img = None
        self.setZValue(2)  # تحت باقي الرسومات

    def pad(self):
        return 10

    def process(self, img):
        w, h = img.width(), img.height()
        f = max(2, int(self.props.get("strength", 12)))
        small = img.scaled(max(1, w // f), max(1, h // f), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        if self.mode == "pixel":
            return small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        mid = small.scaled(max(1, w // 2), max(1, h // 2), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return mid.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def draw(self, p):
        sr = self.mapRectToScene(self.r).intersected(QRectF(self.ed.base.rect())).toAlignedRect()
        if sr.width() < 2 or sr.height() < 2:
            return
        key = (sr.x(), sr.y(), sr.width(), sr.height(), self.props.get("strength"), self.mode)
        if key != self._key:
            self._img = self.process(self.ed.base.copy(sr))
            self._key = key
        p.drawImage(self.mapRectFromScene(QRectF(sr)), self._img)
        if not self.ed.exporting and not self.isSelected():
            p.setPen(QPen(QColor(255, 255, 255, 90), 1 / self._lod, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.r)


class SpotAnno(RectAnno):
    shadow_ok = False

    def __init__(self, ed, props):
        super().__init__(ed, props)
        self.setZValue(1)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            self.prepareGeometryChange()
        return super().itemChange(change, value)

    def boundingRect(self):
        full = self.mapRectFromScene(QRectF(self.ed.base.rect()))
        return full.united(super().boundingRect())

    def body_path(self):
        p = QPainterPath()
        p.addEllipse(self.r)
        return p

    def draw(self, p):
        path = QPainterPath()
        path.addRect(self.mapRectFromScene(QRectF(self.ed.base.rect())))
        path.addEllipse(self.r)
        path.setFillRule(Qt.OddEvenFill)
        p.fillPath(path, QColor(0, 0, 0, int(self.ed.cfg.get("spot_dim", 150))))


class BalloonText(QGraphicsTextItem):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        c = self.textCursor()
        c.clearSelection()
        self.setTextCursor(c)
        self.owner.ed.schedule_export()

    def paint(self, p, opt, w=None):
        if self.owner.ed.exporting:
            draw_doc(p, self)
        else:
            opt.state &= ~QStyle.State_Selected
            super().paint(p, opt, w)


class BalloonAnno(RectAnno):
    def __init__(self, ed, props):
        super().__init__(ed, props)
        self.tail = QPointF()
        self.txt = BalloonText(self)
        self.txt.document().contentsChanged.connect(self.fit_text)
        self.on_props()

    def bg(self):
        f = QColor(self.props["fill"])
        return f if f.alpha() > 0 else QColor("white")

    def on_props(self):
        f = QFont("Segoe UI")
        f.setPixelSize(max(8, int(self.props["font_size"] * 0.8)))
        f.setBold(True)
        self.txt.setFont(f)
        self.txt.setDefaultTextColor(contrast(self.bg()))
        self.on_geom()

    def update_drag(self, p0, p1, mods):
        super().update_drag(p0, p1, mods)
        r = self.r
        self.tail = QPointF(r.left() + r.width() * 0.25, r.bottom() + max(24.0, r.height() * 0.45))

    def on_geom(self):
        if not hasattr(self, "txt"):
            return
        self.txt.setTextWidth(max(20.0, self.r.width() - 20))
        self.txt.setPos(self.r.left() + 10, self.r.top() + 8)

    def fit_text(self):
        need = self.txt.boundingRect().height() + 16
        if need > self.r.height():
            self.prepareGeometryChange()
            self.r.setHeight(need)
            self.on_geom()
        self.ed.schedule_export()

    def core_rect(self):
        return self.r.united(QRectF(self.tail, QSizeF1))

    def body_path(self):
        p = QPainterPath()
        p.addRoundedRect(self.r, 12, 12)
        c = self.r.center()
        v = self.tail - c
        L = math.hypot(v.x(), v.y()) or 1
        n = QPointF(-v.y() / L, v.x() / L) * min(self.r.width(), self.r.height()) * 0.18
        tri = QPainterPath()
        tri.addPolygon(QPolygonF([c + n, self.tail, c - n, c + n]))
        return p.united(tri)

    def geom(self):
        return (QRectF(self.r), QPointF(self.tail))

    def set_geom(self, g):
        self.prepareGeometryChange()
        self.r, self.tail = QRectF(g[0]), QPointF(g[1])
        self.on_geom()
        self.update()

    def handles(self):
        return super().handles() + [self.tail]

    def move_handle(self, i, p, mods):
        if i == 4:
            self.tail = p
        else:
            super().move_handle(i, p, mods)

    def draw(self, p):
        p.setPen(self.pen())
        p.setBrush(self.bg())
        p.drawPath(self.body_path().simplified())

    def creating_done(self):
        self.start_edit()

    def start_edit(self):
        self.txt.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.txt.setFocus()
        c = self.txt.textCursor()
        c.movePosition(QTextCursor.End)
        self.txt.setTextCursor(c)

    def mouseDoubleClickEvent(self, e):
        self.start_edit()


QSizeF1 = QRectF(0, 0, 1, 1).size()


class LineAnno(Anno):
    def __init__(self, ed, props):
        super().__init__(ed, props)
        self.a = QPointF()
        self.b = QPointF()

    def core_rect(self):
        return QRectF(self.a, self.b).normalized()

    def update_drag(self, p0, p1, mods):
        self.prepareGeometryChange()
        self.a = p0
        if mods & Qt.ShiftModifier:
            ang = math.atan2(p1.y() - p0.y(), p1.x() - p0.x())
            ang = round(ang / (math.pi / 4)) * (math.pi / 4)
            L = QLineF(p0, p1).length()
            p1 = QPointF(p0.x() + L * math.cos(ang), p0.y() + L * math.sin(ang))
        self.b = p1
        self.update()

    def is_valid(self):
        return QLineF(self.a, self.b).length() > 4

    def geom(self):
        return (QPointF(self.a), QPointF(self.b))

    def set_geom(self, g):
        self.prepareGeometryChange()
        self.a, self.b = QPointF(g[0]), QPointF(g[1])
        self.update()

    def handles(self):
        return [self.a, self.b]

    def move_handle(self, i, p, mods):
        if i == 0:
            self.a = p
        else:
            self.b = p

    def body_path(self):
        path = QPainterPath(self.a)
        path.lineTo(self.b)
        s = QPainterPathStroker()
        s.setWidth(max(self.props["width"], 4) + 10)
        return s.createStroke(path)

    def pen(self):
        return QPen(QColor(self.props["color"]), self.props["width"], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    def draw(self, p):
        p.setPen(self.pen())
        p.drawLine(self.a, self.b)

    def draw_selection(self, p):  # بس النقاط، بدون مربع
        s = 5 / self._lod
        p.setPen(QPen(QColor(0, 120, 215), 1.5 / self._lod))
        p.setBrush(QColor("white"))
        for h in self.handles():
            p.drawEllipse(h, s, s)


class ArrowAnno(LineAnno):
    def head(self):
        return max(12.0, self.props["width"] * 3.6)

    def pad(self):
        return self.head() + 12

    def draw(self, p):
        L = QLineF(self.a, self.b)
        if L.length() < 1:
            return
        hl = min(self.head(), L.length())
        ang = math.atan2(self.b.y() - self.a.y(), self.b.x() - self.a.x())
        base = QPointF(self.b.x() - math.cos(ang) * hl * 0.8, self.b.y() - math.sin(ang) * hl * 0.8)
        p.setPen(self.pen())
        p.drawLine(self.a, base)
        w = 0.42
        p1 = QPointF(self.b.x() - hl * math.cos(ang - w), self.b.y() - hl * math.sin(ang - w))
        p2 = QPointF(self.b.x() - hl * math.cos(ang + w), self.b.y() - hl * math.sin(ang + w))
        c = QColor(self.props["color"])
        p.setPen(QPen(c, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(c)
        p.drawPolygon(QPolygonF([self.b, p1, p2]))


class PenAnno(Anno):
    def __init__(self, ed, props, highlight=False):
        self.highlight = highlight
        self.shadow_ok = not highlight
        super().__init__(ed, props)
        self.pts = []
        self._path = None

    def update_drag(self, p0, p1, mods):
        self.prepareGeometryChange()
        if not self.pts:
            self.pts = [p0]
        if mods & Qt.ShiftModifier:
            self.pts = [self.pts[0], p1]
        elif QLineF(self.pts[-1], p1).length() > 1.2:
            self.pts.append(p1)
        self._path = None
        self.update()

    def path(self):
        if self._path is None:
            path = QPainterPath()
            if self.pts:
                path.moveTo(self.pts[0])
                if len(self.pts) == 2:
                    path.lineTo(self.pts[1])
                for i in range(1, len(self.pts) - 1):
                    mid = (self.pts[i] + self.pts[i + 1]) / 2
                    path.quadTo(self.pts[i], mid)
                if len(self.pts) > 2:
                    path.lineTo(self.pts[-1])
            self._path = path
        return self._path

    def width(self):
        w = self.props["width"]
        return max(14, w * 4) if self.highlight else w

    def pad(self):
        return self.width() / 2 + 12

    def core_rect(self):
        return self.path().boundingRect()

    def is_valid(self):
        return len(self.pts) >= 2

    def geom(self):
        return [QPointF(p) for p in self.pts]

    def set_geom(self, g):
        self.prepareGeometryChange()
        self.pts = [QPointF(p) for p in g]
        self._path = None
        self.update()

    def body_path(self):
        s = QPainterPathStroker()
        s.setWidth(self.width() + 8)
        return s.createStroke(self.path())

    def draw(self, p):
        c = QColor(self.props["color"])
        if self.highlight:
            c.setAlpha(110)
            p.setCompositionMode(QPainter.CompositionMode_Multiply)
        p.setPen(QPen(c, self.width(), Qt.SolidLine, Qt.FlatCap if self.highlight else Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(self.path())
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)


class StepAnno(Anno):
    def __init__(self, ed, props, n, c):
        super().__init__(ed, props)
        self.n = n
        self.c = QPointF(c)

    def R(self):
        return 11 + self.props["width"] * 2.2

    def core_rect(self):
        R = self.R()
        return QRectF(self.c.x() - R, self.c.y() - R, 2 * R, 2 * R)

    def body_path(self):
        p = QPainterPath()
        p.addEllipse(self.core_rect())
        return p

    def geom(self):
        return QPointF(self.c)

    def set_geom(self, g):
        self.prepareGeometryChange()
        self.c = QPointF(g)

    def draw(self, p):
        col = QColor(self.props["color"])
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(col)
        p.drawEllipse(self.core_rect())
        f = QFont("Segoe UI")
        f.setBold(True)
        f.setPixelSize(int(self.R() * (1.05 if self.n < 10 else 0.85)))
        p.setFont(f)
        p.setPen(contrast(col))
        p.drawText(self.core_rect(), Qt.AlignCenter, str(self.n))


class EmojiAnno(Anno):
    def __init__(self, ed, props, c):
        super().__init__(ed, props)
        self.c = QPointF(c)

    def font(self):
        f = QFont("Segoe UI Emoji")
        f.setPixelSize(int(self.props["font_size"] * 1.8))
        return f

    def core_rect(self):
        fm = QFontMetricsF(self.font())
        w = fm.horizontalAdvance(self.props["emoji"]) + 4
        h = fm.height()
        return QRectF(self.c.x() - w / 2, self.c.y() - h / 2, w, h)

    def geom(self):
        return QPointF(self.c)

    def set_geom(self, g):
        self.prepareGeometryChange()
        self.c = QPointF(g)

    def draw(self, p):
        p.setFont(self.font())
        p.setPen(QColor("black"))
        p.drawText(self.core_rect(), Qt.AlignCenter, self.props["emoji"])


class TextAnno(QGraphicsTextItem):
    def __init__(self, ed, props):
        super().__init__()
        self.ed = ed
        self.props = dict(props)
        self._added = False
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsFocusable)
        self.setZValue(ed.next_z())
        self.apply()
        self.document().contentsChanged.connect(ed.schedule_export)

    def apply(self):
        f = QFont("Segoe UI")
        f.setPixelSize(int(self.props["font_size"]))
        f.setBold(True)
        self.setFont(f)
        self.setDefaultTextColor(QColor(self.props["color"]))
        set_shadow(self, self.props.get("shadow"))

    def set_prop(self, k, v):
        self.prepareGeometryChange()
        self.props[k] = v
        self.apply()
        self.update()

    def geom(self):
        return None

    def set_geom(self, g):
        pass

    def start_edit(self):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus()
        c = self.textCursor()
        c.movePosition(QTextCursor.End)
        self.setTextCursor(c)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        c = self.textCursor()
        c.clearSelection()
        self.setTextCursor(c)
        self.ed.text_finished(self)

    def mouseDoubleClickEvent(self, e):
        self.start_edit()
        super().mouseDoubleClickEvent(e)

    def paint(self, p, opt, w=None):
        fill = QColor(self.props["fill"])
        if fill.alpha() > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(super().boundingRect(), 6, 6)
        if self.ed.exporting:
            draw_doc(p, self)
            return
        opt.state &= ~QStyle.State_Selected
        super().paint(p, opt, w)
        if self.isSelected() or self.hasFocus():
            lod = max(0.05, QStyleOptionGraphicsItem.levelOfDetailFromTransform(p.worldTransform()))
            p.setPen(QPen(QColor(0, 150, 255), 1 / lod, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(super().boundingRect())


# ───────────────────────────── undo commands ─────────────────────────────

class AddCmd(QUndoCommand):
    def __init__(self, ed, item):
        super().__init__("إضافة")
        self.ed, self.item = ed, item
        item._added = True

    def redo(self):
        if self.item.scene() is None:
            self.ed.scene.addItem(self.item)

    def undo(self):
        self.item.setSelected(False)
        self.ed.scene.removeItem(self.item)


class RemoveCmd(QUndoCommand):
    def __init__(self, ed, items):
        super().__init__("حذف")
        self.ed, self.items = ed, list(items)

    def redo(self):
        for i in self.items:
            if i.scene():
                i.setSelected(False)
                self.ed.scene.removeItem(i)

    def undo(self):
        for i in self.items:
            if i.scene() is None:
                self.ed.scene.addItem(i)


class StateCmd(QUndoCommand):
    def __init__(self, before, after):
        super().__init__("تحريك")
        self.before, self.after = before, after

    @staticmethod
    def apply(st):
        for item, (pos, g) in st.items():
            item.setPos(pos)
            if g is not None:
                item.set_geom(g)

    def redo(self):
        self.apply(self.after)

    def undo(self):
        self.apply(self.before)


class PropCmd(QUndoCommand):
    def __init__(self, items, k, v):
        super().__init__("تعديل")
        self.items, self.k, self.v = items, k, v
        self.olds = [i.props.get(k) for i in items]

    def redo(self):
        for i in self.items:
            i.set_prop(self.k, self.v)

    def undo(self):
        for i, o in zip(self.items, self.olds):
            i.set_prop(self.k, o)


class CropCmd(QUndoCommand):
    def __init__(self, ed, old, new):
        super().__init__("قص")
        self.ed, self.old, self.new = ed, QRectF(old), QRectF(new)

    def redo(self):
        self.ed.set_canvas(self.new)

    def undo(self):
        self.ed.set_canvas(self.old)


# ───────────────────────────── editor view ─────────────────────────────

class View(QGraphicsView):
    def __init__(self, ed):
        super().__init__(ed.scene)
        self.ed = ed
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setBackgroundBrush(QColor("#16181d"))
        self.setFrameShape(QFrame.NoFrame)
        self._creating = None
        self._p0 = None
        self._pan = None
        self._before = None
        self._crop = None

    def sp(self, e):
        return self.mapToScene(e.position().toPoint())

    def mousePressEvent(self, e):
        ed = self.ed
        if e.button() == Qt.MiddleButton:
            self._pan = e.position()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        sp = self.sp(e)
        anno = ed.anno_of(self.itemAt(e.position().toPoint()))
        handle_hit = isinstance(anno, Anno) and anno.isSelected() and \
            anno.hit_handle(anno.mapFromScene(sp)) is not None

        if ed.tool == "select" or handle_hit:
            self._before = ed.snapshot()
            return super().mousePressEvent(e)

        if ed.is_editing_text():
            # كبسة برا النص = خلّص كتابة
            if isinstance(anno, TextAnno) and anno.hasFocus():
                return super().mousePressEvent(e)
            ed.scene.clearFocus()
            ed.scene.setFocusItem(None)
            return

        if ed.tool == "text":
            if isinstance(anno, TextAnno):
                super().mousePressEvent(e)
                anno.start_edit()
                return
            ed.create_text(sp)
            return
        if ed.tool == "crop":
            self._crop = sp
            ed.crop_preview = QRectF(sp, sp)
            return
        if ed.tool in ("step", "emoji"):
            ed.create_click(ed.tool, sp)
            return
        item = ed.make_item(ed.tool)
        ed.scene.clearSelection()
        ed.scene.addItem(item)
        self._creating, self._p0 = item, sp
        item.update_drag(sp, sp, e.modifiers())

    def mouseMoveEvent(self, e):
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self._creating is not None:
            self._creating.update_drag(self._p0, self.sp(e), e.modifiers())
            return
        if self._crop is not None:
            self.ed.crop_preview = QRectF(self._crop, self.sp(e)).normalized()
            self.viewport().update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan is not None and e.button() == Qt.MiddleButton:
            self._pan = None
            self.ed.apply_cursor()
            return
        if self._creating is not None:
            it, self._creating = self._creating, None
            self.ed.finish_create(it)
            return
        if self._crop is not None:
            r = self.ed.crop_preview
            self._crop = None
            self.ed.crop_preview = None
            self.ed.do_crop(r)
            self.viewport().update()
            return
        super().mouseReleaseEvent(e)
        if self._before is not None:
            self.ed.commit_state(self._before)
            self._before = None

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            f = 1.15 ** (e.angleDelta().y() / 120)
            self.scale(f, f)
            self.ed.update_zoom()
            return
        super().wheelEvent(e)

    def drawForeground(self, painter, rect):
        ed = self.ed
        full = rect.united(QRectF(ed.base.rect())).adjusted(-5000, -5000, 5000, 5000)
        if ed.canvas != QRectF(ed.base.rect()):
            path = QPainterPath()
            path.addRect(full)
            path.addRect(ed.canvas)
            path.setFillRule(Qt.OddEvenFill)
            painter.fillPath(path, QColor(22, 24, 29, 240))
        if ed.crop_preview is not None:
            c = ed.crop_preview
            path = QPainterPath()
            path.addRect(ed.canvas)
            path.addRect(c)
            path.setFillRule(Qt.OddEvenFill)
            painter.fillPath(path, QColor(0, 0, 0, 140))
            lod = self.transform().m11() or 1
            painter.setPen(QPen(QColor("#ffd166"), 1.5 / lod, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(c)
            f = QFont("Segoe UI")
            f.setPixelSize(max(8, int(13 / lod)))
            painter.setFont(f)
            painter.setPen(QColor("#ffd166"))
            painter.drawText(c.topLeft() + QPointF(4 / lod, -6 / lod), f"{int(c.width())} × {int(c.height())}")


# ───────────────────────────── editor window ─────────────────────────────

EDITOR_QSS = """
QMainWindow, QWidget { background:#1f2229; color:#e8e8e8; font-family:'Segoe UI'; font-size:13px; }
QToolBar { background:#262a33; border:none; spacing:3px; padding:4px; }
QToolButton { background:transparent; border:1px solid transparent; border-radius:7px; padding:4px 7px; font-size:17px; }
QToolButton:hover { background:#333845; border-color:#3f4554; }
QToolButton:checked { background:#6c5ce7; border-color:#7d6ff0; }
QToolButton#small { font-size:12px; padding:3px 8px; }
QToolButton#done { background:#2ecc71; color:#0b2615; font-weight:bold; font-size:14px; padding:5px 14px; }
QToolButton#done:hover { background:#44d986; }
QSpinBox, QComboBox { background:#2d313b; border:1px solid #3f4554; border-radius:5px; padding:2px 4px; min-width:52px; }
QCheckBox { spacing:5px; }
QLabel#muted { color:#9aa0ab; }
QStatusBar { background:#1a1d23; color:#9aa0ab; }
QMenu { background:#262a33; border:1px solid #3f4554; }
QMenu::item:selected { background:#6c5ce7; }
"""


class Editor(QMainWindow):
    def __init__(self, app, img, path=None):
        super().__init__()
        self.app = app
        self.cfg = app.cfg
        self.setWindowTitle(f"{APP_TITLE} — {img.width()}×{img.height()}")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(EDITOR_QSS)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.base = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self.canvas = QRectF(self.base.rect())
        self.crop_preview = None
        self.exporting = False
        self._quiet = False
        self._z = 10
        self.props = {k: self.cfg[k] for k in ("color", "fill", "width", "font_size", "shadow", "strength", "emoji")}

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(self.canvas)
        bg = self.scene.addPixmap(QPixmap.fromImage(self.base))
        bg.setZValue(-100)
        bg.setTransformationMode(Qt.SmoothTransformation)
        self.view = View(self)
        self.setCentralWidget(self.view)

        self.undo = QUndoStack(self)
        self.undo.indexChanged.connect(self.schedule_export)
        self.export_timer = QTimer(self, singleShot=True, interval=200, timeout=self.export_now)

        if path:
            self.file_path = Path(path)
        else:
            name = datetime.datetime.now().strftime(self.cfg["name_pattern"]) + "." + self.cfg["format"]
            self.file_path = Path(self.cfg["save_dir"]) / name

        self.build_toolbars()
        self.build_status()
        self.scene.selectionChanged.connect(self.on_selection)
        self.set_tool(self.cfg.get("last_tool", "rect"))
        if not path and self.cfg["auto_save"]:
            self.save_to(self.file_path, self.base)

    # ---------- UI ----------
    def build_toolbars(self):
        tb = QToolBar("أدوات")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.TopToolBarArea, tb)
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for tid, glyph, name, key in TOOLS:
            a = QAction(glyph, self, checkable=True)
            a.setToolTip(f"{name}  ({key})")
            a.triggered.connect(lambda _=False, t=tid: self.set_tool(t))
            self.tool_group.addAction(a)
            tb.addAction(a)
            self.tool_actions[tid] = a
            if tid in ("select", "highlight", "emoji", "spot"):
                tb.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        def act(glyph, tip, fn, shortcut=None):
            a = QAction(glyph, self)
            a.setToolTip(tip + (f"  ({shortcut})" if shortcut else ""))
            a.triggered.connect(fn)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            tb.addAction(a)
            return a

        act("↶", "تراجع", self.undo.undo, "Ctrl+Z")
        act("↷", "إعادة", self.undo.redo, "Ctrl+Y")
        a = QAction(self)
        a.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        a.triggered.connect(self.undo.redo)
        self.addAction(a)
        act("🗑", "حذف المحدد  (Delete)", self.delete_selected)
        tb.addSeparator()
        act("📋", "نسخ للحافظة", self.copy_now, "Ctrl+C")
        act("💾", "حفظ باسم…", self.save_as, "Ctrl+S")
        act("📁", "افتح فولدر الصور", self.app.open_folder)
        act("⚙", "الإعدادات", self.app.show_settings)
        done = QToolButton()
        done.setObjectName("done")
        done.setText("✔ تم")
        done.setToolTip("نسخ وإغلاق  (Enter)")
        done.clicked.connect(self.finish)
        tb.addWidget(done)

        self.addToolBarBreak()
        ob = QToolBar("خيارات")
        ob.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, ob)
        self.opt_actions = {}

        def label(t):
            l = QLabel(t)
            l.setObjectName("muted")
            return l

        ob.addWidget(label(" اللون "))
        self.color_btn = QToolButton()
        self.color_btn.setToolTip("اختار لون")
        self.color_btn.clicked.connect(lambda: self.pick_color("color"))
        ob.addWidget(self.color_btn)
        for c in PALETTE:
            b = QToolButton()
            b.setFixedSize(20, 20)
            b.setStyleSheet(f"QToolButton{{background:{c};border:1px solid #555;border-radius:10px;padding:0}}"
                            f"QToolButton:hover{{border:2px solid white}}")
            b.clicked.connect(lambda _=False, c=c: self.set_prop("color", c))
            ob.addWidget(b)
        ob.addSeparator()

        ob.addWidget(label(" تعبئة "))
        self.fill_btn = QToolButton()
        self.fill_btn.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.fill_btn)
        m.addAction("بدون تعبئة", lambda: self.set_prop("fill", "#00000000"))
        m.addAction("اختار لون…", lambda: self.pick_color("fill"))
        m.addSeparator()
        for c in PALETTE:
            fc = QColor(c)
            fc.setAlpha(110)
            m.addAction(swatch_icon(fc.name(QColor.HexArgb)), "شفاف",
                        lambda c=fc.name(QColor.HexArgb): self.set_prop("fill", c))
            m.addAction(swatch_icon(c), "كامل", lambda c=c: self.set_prop("fill", c))
        self.fill_btn.setMenu(m)
        ob.addWidget(self.fill_btn)
        ob.addSeparator()

        self.width_spin = QSpinBox(minimum=1, maximum=40, suffix=" px")
        self.width_spin.setToolTip("سُمك الخط")
        self.width_spin.valueChanged.connect(lambda v: self.set_prop("width", v))
        self.opt_actions["width_l"] = ob.addWidget(label(" السُمك "))
        self.opt_actions["width"] = ob.addWidget(self.width_spin)

        self.font_spin = QSpinBox(minimum=8, maximum=200)
        self.font_spin.setToolTip("حجم الخط / الإيموجي")
        self.font_spin.valueChanged.connect(lambda v: self.set_prop("font_size", v))
        self.opt_actions["font_l"] = ob.addWidget(label(" حجم الخط "))
        self.opt_actions["font"] = ob.addWidget(self.font_spin)

        self.strength_spin = QSpinBox(minimum=2, maximum=60)
        self.strength_spin.setToolTip("قوة التغبيش / حجم البكسل")
        self.strength_spin.valueChanged.connect(lambda v: self.set_prop("strength", v))
        self.opt_actions["strength_l"] = ob.addWidget(label(" القوة "))
        self.opt_actions["strength"] = ob.addWidget(self.strength_spin)

        self.emoji_btn = QToolButton()
        self.emoji_btn.setPopupMode(QToolButton.InstantPopup)
        em = QMenu(self.emoji_btn)
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(2)
        for i, ch in enumerate(EMOJIS):
            b = QToolButton()
            b.setText(ch)
            b.setStyleSheet("font-size:20px;padding:2px")
            b.clicked.connect(lambda _=False, ch=ch: (self.set_prop("emoji", ch), em.close()))
            grid.addWidget(b, i // 8, i % 8)
        wa = QWidgetAction(em)
        wa.setDefaultWidget(grid_w)
        em.addAction(wa)
        self.emoji_btn.setMenu(em)
        self.opt_actions["emoji_l"] = ob.addWidget(label(" الإيموجي "))
        self.opt_actions["emoji"] = ob.addWidget(self.emoji_btn)

        ob.addSeparator()
        self.shadow_chk = QCheckBox("ظل")
        self.shadow_chk.toggled.connect(lambda v: self.set_prop("shadow", v))
        ob.addWidget(self.shadow_chk)

        sp2 = QWidget()
        sp2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ob.addWidget(sp2)
        self.zoom_lbl = label("100%")
        ob.addWidget(self.zoom_lbl)
        for txt, tip, fn in (("⤢", "ملاءمة للشاشة  (Ctrl+0)", self.fit), ("1:1", "الحجم الحقيقي", self.actual_size)):
            b = QToolButton()
            b.setObjectName("small")
            b.setText(txt)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            ob.addWidget(b)
        a = QAction(self)
        a.setShortcut(QKeySequence("Ctrl+0"))
        a.triggered.connect(self.fit)
        self.addAction(a)
        self.load_props_ui(self.props)

    def build_status(self):
        sb = self.statusBar()
        self.status_lbl = QLabel("جاهز")
        sb.addWidget(self.status_lbl, 1)
        self.path_lbl = QLabel()
        self.path_lbl.setObjectName("muted")
        self.path_lbl.setText(f"{self.base.width()}×{self.base.height()}   •   " +
                              (str(self.file_path) if self.cfg["auto_save"] else "الحفظ التلقائي مطفي"))
        sb.addPermanentWidget(self.path_lbl)
        hint = QLabel("Shift = خطوط مستقيمة/مربع   •   Ctrl+عجلة = زوم   •   زر الماوس الأوسط = تحريك الصورة")
        hint.setObjectName("muted")
        sb.addPermanentWidget(hint)

    def load_props_ui(self, props):
        for w in (self.width_spin, self.font_spin, self.strength_spin, self.shadow_chk):
            w.blockSignals(True)
        self.width_spin.setValue(int(props.get("width", 4)))
        self.font_spin.setValue(int(props.get("font_size", 28)))
        self.strength_spin.setValue(int(props.get("strength", 12)))
        self.shadow_chk.setChecked(bool(props.get("shadow", True)))
        for w in (self.width_spin, self.font_spin, self.strength_spin, self.shadow_chk):
            w.blockSignals(False)
        self.color_btn.setIcon(swatch_icon(props.get("color", "#e53935")))
        self.fill_btn.setIcon(swatch_icon(props.get("fill", "#00000000")))
        self.emoji_btn.setText(props.get("emoji", "😀"))

    def update_option_visibility(self):
        t = self.tool
        show = {
            "width": t not in ("text", "emoji", "blur", "pixel", "spot", "crop"),
            "font": t in ("text", "balloon", "emoji", "select"),
            "strength": t in ("blur", "pixel"),
            "emoji": t in ("emoji",),
        }
        for k, v in show.items():
            self.opt_actions[k].setVisible(v)
            self.opt_actions[k + "_l"].setVisible(v)

    # ---------- tools ----------
    def set_tool(self, t):
        if t not in self.tool_actions:
            t = "rect"
        if self.is_editing_text():
            self.scene.clearFocus()
        self.tool = t
        self.tool_actions[t].setChecked(True)
        self.view.setDragMode(QGraphicsView.RubberBandDrag if t == "select" else QGraphicsView.NoDrag)
        self.apply_cursor()
        self.update_option_visibility()
        if t != "crop":
            self.cfg["last_tool"] = t

    def apply_cursor(self):
        cur = {"select": Qt.ArrowCursor, "text": Qt.IBeamCursor}.get(self.tool, Qt.CrossCursor)
        self.view.viewport().setCursor(cur)

    def next_z(self):
        self._z += 1
        return self._z

    def next_step(self):
        nums = [i.n for i in self.scene.items() if isinstance(i, StepAnno)]
        return max(nums, default=0) + 1

    def make_item(self, tool):
        p = dict(self.props)
        return {
            "rect": lambda: RectAnno(self, p),
            "ellipse": lambda: EllipseAnno(self, p),
            "line": lambda: LineAnno(self, p),
            "arrow": lambda: ArrowAnno(self, p),
            "pen": lambda: PenAnno(self, p),
            "highlight": lambda: PenAnno(self, p, highlight=True),
            "balloon": lambda: BalloonAnno(self, p),
            "blur": lambda: BlurAnno(self, p, "blur"),
            "pixel": lambda: BlurAnno(self, p, "pixel"),
            "spot": lambda: SpotAnno(self, p),
        }[tool]()

    def finish_create(self, it):
        if not it.is_valid():
            self.scene.removeItem(it)
            return
        self.undo.push(AddCmd(self, it))
        if isinstance(it, (RectAnno, LineAnno)):
            self.scene.clearSelection()
            it.setSelected(True)
        it.creating_done()

    def create_click(self, tool, sp):
        p = dict(self.props)
        it = StepAnno(self, p, self.next_step(), sp) if tool == "step" else EmojiAnno(self, p, sp)
        self.scene.clearSelection()
        self.scene.addItem(it)
        self.undo.push(AddCmd(self, it))

    def create_text(self, sp):
        t = TextAnno(self, dict(self.props))
        t.setPos(sp - QPointF(4, self.props["font_size"] * 0.75))
        self.scene.clearSelection()
        self.scene.addItem(t)
        t.start_edit()

    def text_finished(self, t):
        if t.scene() is None:
            return
        empty = not t.toPlainText().strip()
        if empty:
            if t._added:
                self.undo.push(RemoveCmd(self, [t]))
            else:
                self.scene.removeItem(t)
        elif not t._added:
            self.undo.push(AddCmd(self, t))
        self.schedule_export()

    def is_editing_text(self):
        f = self.scene.focusItem()
        return isinstance(f, QGraphicsTextItem) and bool(f.textInteractionFlags() & Qt.TextEditorInteraction)

    def anno_of(self, item):
        while item is not None and not isinstance(item, (Anno, TextAnno)):
            item = item.parentItem()
        return item

    def annos(self):
        return [i for i in self.scene.items() if isinstance(i, (Anno, TextAnno))]

    def selected_annos(self):
        out = []
        for i in self.scene.selectedItems():
            a = self.anno_of(i)
            if a is not None and a not in out:
                out.append(a)
        return out

    def snapshot(self):
        return {i: (QPointF(i.pos()), i.geom()) for i in self.annos()}

    def commit_state(self, before):
        after = self.snapshot()
        changed_b, changed_a = {}, {}
        for item, (pos, g) in after.items():
            if item in before:
                bp, bg = before[item]
                if bp != pos or bg != g:
                    changed_b[item] = (bp, bg)
                    changed_a[item] = (pos, g)
        if changed_a:
            self.undo.push(StateCmd(changed_b, changed_a))

    def set_prop(self, k, v):
        self.props[k] = v
        self.cfg[k] = v
        self.load_props_ui(self.props)
        items = [i for i in self.selected_annos() if k in i.props]
        if items:
            self.undo.push(PropCmd(items, k, v))

    def pick_color(self, k):
        c = QColorDialog.getColor(QColor(self.props[k]), self, "اختار لون", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.set_prop(k, c.name(QColor.HexArgb) if c.alpha() < 255 else c.name())

    def on_selection(self):
        if self._quiet:
            return
        sel = self.selected_annos()
        if len(sel) == 1:
            self.load_props_ui({**self.props, **sel[0].props})

    def delete_selected(self):
        sel = self.selected_annos()
        if sel:
            self.undo.push(RemoveCmd(self, sel))

    # ---------- crop / zoom ----------
    def do_crop(self, r):
        if r is None:
            return
        r = QRectF(r.intersected(self.canvas).toAlignedRect())
        if r.width() < 5 or r.height() < 5:
            return
        self.undo.push(CropCmd(self, self.canvas, r))
        self.set_tool("select")

    def set_canvas(self, r):
        self.canvas = QRectF(r)
        self.scene.setSceneRect(self.canvas)
        self.view.viewport().update()
        QTimer.singleShot(0, self.fit)

    def fit(self):
        dpr = self.devicePixelRatioF() or 1
        vp = self.view.viewport().size()
        s = min((vp.width() - 30) / max(1, self.canvas.width()),
                (vp.height() - 30) / max(1, self.canvas.height()), 1 / dpr)
        self.view.resetTransform()
        self.view.scale(s, s)
        self.view.centerOn(self.canvas.center())
        self.update_zoom()

    def actual_size(self):
        dpr = self.devicePixelRatioF() or 1
        self.view.resetTransform()
        self.view.scale(1 / dpr, 1 / dpr)
        self.update_zoom()

    def update_zoom(self):
        dpr = self.devicePixelRatioF() or 1
        self.zoom_lbl.setText(f"{round(self.view.transform().m11() * dpr * 100)}%  ")

    # ---------- export ----------
    def schedule_export(self, *_):
        self.export_timer.start()

    def render(self):
        self.exporting = True
        self._quiet = True
        sel = self.scene.selectedItems()
        for i in sel:
            i.setSelected(False)
        r = self.canvas
        img = QImage(int(r.width()), int(r.height()), QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.scene.render(p, QRectF(img.rect()), r)
        p.end()
        for i in sel:
            i.setSelected(True)
        self._quiet = False
        self.exporting = False
        return img

    def export_now(self, force_copy=False):
        self.export_timer.stop()
        img = self.render()
        msgs = []
        if self.cfg["auto_copy"] or force_copy:
            self.app.set_clipboard(img)
            msgs.append("✓ اتنسخت للحافظة — Ctrl+V بأي مكان")
        if self.cfg["auto_save"]:
            if self.save_to(self.file_path, img):
                msgs.append("💾 انحفظت")
        self.status_lbl.setText("   ".join(msgs) + "   " + datetime.datetime.now().strftime("%H:%M:%S"))
        return img

    def save_to(self, path, img):
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() in (".jpg", ".jpeg"):
                out = QImage(img.size(), QImage.Format_RGB32)
                out.fill(Qt.white)
                p = QPainter(out)
                p.drawImage(0, 0, img)
                p.end()
                return out.save(str(path), "JPG", int(self.cfg["jpg_quality"]))
            return img.save(str(path), "PNG")
        except Exception:
            return False

    def copy_now(self):
        self.export_now(force_copy=True)

    def save_as(self):
        fn, _ = QFileDialog.getSaveFileName(self, "حفظ باسم", str(self.file_path), "PNG (*.png);;JPG (*.jpg)")
        if fn:
            self.save_to(fn, self.render())
            self.status_lbl.setText(f"💾 انحفظت: {fn}")

    def finish(self):
        if self.is_editing_text():
            self.scene.clearFocus()
        self.export_now(force_copy=True)
        self.close()

    # ---------- window ----------
    def present(self):
        if self.cfg["maximized"]:
            self.showMaximized()
        else:
            scr = QApplication.primaryScreen().availableGeometry()
            self.resize(int(scr.width() * 0.8), int(scr.height() * 0.8))
            self.show()
        self.raise_()
        self.activateWindow()
        force_foreground(int(self.winId()), keep_top=self.cfg["always_on_top"])
        QTimer.singleShot(60, self.fit if self.cfg["fit_on_open"] else self.actual_size)
        self.view.setFocus()

    def keyPressEvent(self, e):
        if self.is_editing_text():
            if e.key() == Qt.Key_Escape:
                self.scene.clearFocus()
                return
            return super().keyPressEvent(e)
        k, mods = e.key(), e.modifiers()
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            if self.cfg["enter_closes"]:
                self.finish()
            else:
                self.copy_now()
        elif k == Qt.Key_Escape:
            if self.scene.selectedItems():
                self.scene.clearSelection()
            else:
                self.close()
        elif not mods & (Qt.ControlModifier | Qt.AltModifier):
            vk = e.nativeVirtualKey()  # بيشتغل حتى لو الكيبورد عربي
            ch = chr(vk) if 65 <= vk <= 90 else (e.text() or "").upper()
            if ch in TOOL_KEYS:
                self.set_tool(TOOL_KEYS[ch])
            else:
                super().keyPressEvent(e)
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.export_timer.isActive():
            self.export_now()
        self.cfg.save()
        self.app.editor_closed(self)
        super().closeEvent(e)


# ───────────────────────────── settings dialog ─────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(f"إعدادات {APP_TITLE}")
        self.setWindowIcon(app_icon())
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(520)
        self.setStyleSheet(EDITOR_QSS + "QTabWidget::pane{border:1px solid #3f4554;border-radius:6px}"
                           "QTabBar::tab{background:#262a33;padding:7px 16px}"
                           "QTabBar::tab:selected{background:#6c5ce7}"
                           "QLineEdit{background:#2d313b;border:1px solid #3f4554;border-radius:5px;padding:4px}"
                           "QPushButton{background:#2d313b;border:1px solid #3f4554;border-radius:5px;padding:5px 12px}"
                           "QPushButton:hover{background:#383d49}")
        tabs = QTabWidget()
        self.w = {}

        # عام
        g = QWidget()
        f = QFormLayout(g)
        trig = QComboBox()
        trig.addItem("بس لما أصوّر بـ Win+Shift+S  (منصوح)", "shortcut")
        trig.addItem("أي صورة تنسخ للحافظة", "any")
        trig.setCurrentIndex(0 if cfg["trigger"] == "shortcut" else 1)
        self.w["trigger"] = trig
        f.addRow("متى يفتح المحرر:", trig)
        for key, text in (("also_printscreen", "اعتبر زر Print Screen كمان"),
                          ("open_editor", "افتح المحرر تلقائياً بعد التصوير"),
                          ("start_with_windows", "شغّل لقطة مع Windows"),
                          ("notify", "إشعار لما يشتغل البرنامج")):
            self.w[key] = QCheckBox(text, checked=bool(cfg[key]))
            f.addRow(self.w[key])
        tabs.addTab(g, "عام")

        # الحفظ
        g = QWidget()
        f = QFormLayout(g)
        self.w["auto_copy"] = QCheckBox("انسخ للحافظة تلقائياً بعد كل تعديل", checked=bool(cfg["auto_copy"]))
        self.w["auto_save"] = QCheckBox("احفظ ملف تلقائياً بعد كل تعديل", checked=bool(cfg["auto_save"]))
        f.addRow(self.w["auto_copy"])
        f.addRow(self.w["auto_save"])
        row = QHBoxLayout()
        self.w["save_dir"] = QLineEdit(cfg["save_dir"])
        b = QPushButton("تصفّح…")
        b.clicked.connect(self.browse)
        row.addWidget(self.w["save_dir"])
        row.addWidget(b)
        f.addRow("فولدر الحفظ:", row)
        self.w["name_pattern"] = QLineEdit(cfg["name_pattern"])
        f.addRow("اسم الملف:", self.w["name_pattern"])
        fmt = QComboBox()
        fmt.addItems(["png", "jpg"])
        fmt.setCurrentText(cfg["format"])
        self.w["format"] = fmt
        f.addRow("الصيغة:", fmt)
        self.w["jpg_quality"] = QSpinBox(minimum=40, maximum=100, value=int(cfg["jpg_quality"]))
        f.addRow("جودة JPG:", self.w["jpg_quality"])
        tabs.addTab(g, "الحفظ")

        # المحرر
        g = QWidget()
        f = QFormLayout(g)
        for key, text in (("maximized", "افتح المحرر بملء الشاشة"),
                          ("fit_on_open", "صغّر الصورة لتناسب الشاشة"),
                          ("always_on_top", "المحرر دايماً فوق كل الشبابيك"),
                          ("enter_closes", "Enter = نسخ وإغلاق")):
            self.w[key] = QCheckBox(text, checked=bool(cfg[key]))
            f.addRow(self.w[key])
        self.color = cfg["color"]
        self.color_btn = QPushButton()
        self.color_btn.setIcon(swatch_icon(self.color))
        self.color_btn.setText(self.color)
        self.color_btn.clicked.connect(self.pick)
        f.addRow("اللون الافتراضي:", self.color_btn)
        self.w["width"] = QSpinBox(minimum=1, maximum=40, value=int(cfg["width"]))
        f.addRow("السُمك:", self.w["width"])
        self.w["font_size"] = QSpinBox(minimum=8, maximum=200, value=int(cfg["font_size"]))
        f.addRow("حجم الخط:", self.w["font_size"])
        self.w["shadow"] = QCheckBox("ظل للرسومات", checked=bool(cfg["shadow"]))
        f.addRow(self.w["shadow"])
        sl = QSlider(Qt.Horizontal, minimum=40, maximum=230, value=int(cfg["spot_dim"]))
        self.w["spot_dim"] = sl
        f.addRow("عتمة السبوتلايت:", sl)
        tabs.addTab(g, "المحرر")

        # اختصارات
        g = QWidget()
        v = QVBoxLayout(g)
        txt = "\n".join(f"{k}   ←   {n}" for _, _, n, k in TOOLS)
        txt += ("\n\nEnter   ←   نسخ وإغلاق\nCtrl+C   ←   نسخ\nCtrl+Z / Ctrl+Y   ←   تراجع / إعادة"
                "\nDelete   ←   حذف المحدد\nEsc   ←   إلغاء التحديد / إغلاق\nShift   ←   خط مستقيم / مربع / دائرة"
                "\nCtrl + عجلة الماوس   ←   زوم\nدبل كليك على نص أو فقاعة   ←   تعديل الكتابة")
        lbl = QLabel(txt)
        lbl.setAlignment(Qt.AlignTop)
        v.addWidget(lbl)
        tabs.addTab(g, "الاختصارات")

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("حفظ")
        bb.button(QDialogButtonBox.Cancel).setText("إلغاء")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "فولدر الحفظ", self.w["save_dir"].text())
        if d:
            self.w["save_dir"].setText(d)

    def pick(self):
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.color = c.name()
            self.color_btn.setIcon(swatch_icon(self.color))
            self.color_btn.setText(self.color)

    def values(self):
        out = {"color": self.color}
        for k, w in self.w.items():
            if isinstance(w, QCheckBox):
                out[k] = w.isChecked()
            elif isinstance(w, (QSpinBox, QSlider)):
                out[k] = w.value()
            elif isinstance(w, QLineEdit):
                out[k] = w.text().strip()
            elif k == "trigger":
                out[k] = w.currentData()
            elif isinstance(w, QComboBox):
                out[k] = w.currentText()
        return out


# ───────────────────────────── background app ─────────────────────────────

class KeyWatcher(QObject):
    """بيراقب Win+Shift+S و Print Screen عشان نعرف إنه الصورة الجاية سكرين شوت."""

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.until = 0.0
        self.prev = False
        self.prev_ps = False
        if IS_WIN:
            self.u = ctypes.windll.user32
            self.t = QTimer(self, interval=35, timeout=self.poll)
            self.t.start()

    def down(self, vk):
        return bool(self.u.GetAsyncKeyState(vk) & 0x8000)

    def poll(self):
        s_hit = bool(self.u.GetAsyncKeyState(0x53) & 0x8001)
        combo = (self.down(0x5B) or self.down(0x5C)) and self.down(0x10) and s_hit
        if combo and not self.prev:
            self.arm()
        self.prev = combo
        if self.cfg["also_printscreen"]:
            ps = bool(self.u.GetAsyncKeyState(0x2C) & 0x8001)
            if ps and not self.prev_ps:
                self.arm()
            self.prev_ps = ps

    def arm(self):
        self.until = time.monotonic() + 60

    def armed(self):
        return time.monotonic() < self.until

    def disarm(self):
        self.until = 0.0


class LaqtaApp(QObject):
    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp
        self.cfg = Config()
        self.editors = []
        self.paused = False
        self.last_digest = None
        self.last_time = 0.0
        self.watcher = KeyWatcher(self.cfg)
        self.clip = qapp.clipboard()
        self.clip_timer = QTimer(self, singleShot=True, interval=150, timeout=self.check_clipboard)
        self.clip.dataChanged.connect(self.clip_timer.start)
        self.build_tray()
        set_startup(self.cfg["start_with_windows"])
        self.cfg.save()

    # ---------- tray ----------
    def build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"{APP_TITLE} — شغّالة. صوّر بـ Win+Shift+S")
        m = QMenu()
        m.setLayoutDirection(Qt.RightToLeft)
        m.setStyleSheet(EDITOR_QSS)
        m.addAction("📸  صوّر الآن", self.capture_now)
        m.addAction("📋  عدّل الصورة اللي بالحافظة", self.edit_clipboard)
        self.recent_menu = m.addMenu("🕘  آخر الصور")
        self.recent_menu.aboutToShow.connect(self.fill_recent)
        m.addAction("📁  افتح فولدر الصور", self.open_folder)
        m.addSeparator()
        self.pause_act = m.addAction("⏸  إيقاف مؤقت", self.toggle_pause)
        m.addAction("⚙  الإعدادات", self.show_settings)
        m.addSeparator()
        m.addAction("✖  خروج", self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.edit_clipboard()
                                    if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()
        if self.cfg["notify"]:
            self.tray.showMessage(APP_TITLE, "شغّالة بالخلفية ✓  صوّر بـ Win+Shift+S وبيفتحلك المحرر",
                                  app_icon(), 3500)

    def fill_recent(self):
        self.recent_menu.clear()
        d = Path(self.cfg["save_dir"])
        files = sorted([p for p in d.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")],
                       key=lambda p: p.stat().st_mtime, reverse=True)[:10] if d.exists() else []
        if not files:
            self.recent_menu.addAction("(ما في صور لسا)").setEnabled(False)
        for p in files:
            self.recent_menu.addAction(p.name, lambda p=p: self.open_file(p))

    # ---------- clipboard ----------
    def check_clipboard(self):
        if self.paused or not self.cfg["open_editor"]:
            return
        md = self.clip.mimeData()
        if md is None or md.hasFormat(OWN_MIME) or not md.hasImage():
            return
        if self.cfg["trigger"] == "shortcut" and IS_WIN and not self.watcher.armed():
            return
        img = self.clip.image()
        if img.isNull():
            return
        dg = img_digest(img)
        if dg == self.last_digest and time.monotonic() - self.last_time < 3:
            return
        self.last_digest, self.last_time = dg, time.monotonic()
        self.watcher.disarm()
        self.open_editor(img)

    def set_clipboard(self, img):
        md = QMimeData()
        md.setImageData(img)
        md.setData(OWN_MIME, QByteArray(b"1"))
        self.clip.setMimeData(md)

    # ---------- actions ----------
    def open_editor(self, img, path=None):
        ed = Editor(self, img, path)
        self.editors.append(ed)
        ed.present()
        return ed

    def editor_closed(self, ed):
        if ed in self.editors:
            self.editors.remove(ed)

    def open_file(self, p):
        img = QImage(str(p))
        if not img.isNull():
            self.open_editor(img, p)

    def edit_clipboard(self):
        img = self.clip.image()
        if img.isNull():
            self.tray.showMessage(APP_TITLE, "ما في صورة بالحافظة", app_icon(), 2500)
            return
        self.open_editor(img)

    def capture_now(self):
        self.watcher.arm()
        if IS_WIN:
            os.startfile("ms-screenclip:")

    def open_folder(self):
        self.cfg.fix_save_dir()
        d = Path(self.cfg["save_dir"])
        if IS_WIN:
            os.startfile(str(d))

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_act.setText("▶  تشغيل" if self.paused else "⏸  إيقاف مؤقت")
        self.tray.setToolTip(f"{APP_TITLE} — " + ("موقّفة مؤقتاً" if self.paused else "شغّالة"))

    def show_settings(self):
        dlg = SettingsDialog(self.cfg)
        force_foreground(int(dlg.winId()))
        if dlg.exec():
            self.cfg.update(dlg.values())
            self.cfg.fix_save_dir()
            self.cfg.save()
            set_startup(self.cfg["start_with_windows"])

    def quit(self):
        for ed in list(self.editors):
            ed.close()
        self.cfg.save()
        self.tray.hide()
        self.qapp.quit()


def main():
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Omar.Laqta")
        except Exception:
            pass
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(app_icon())

    # نسخة وحدة بس
    sock = QLocalSocket()
    sock.connectToServer("LaqtaSingleInstance")
    if sock.waitForConnected(300):
        sock.write(b"settings")
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0
    server = QLocalServer()
    QLocalServer.removeServer("LaqtaSingleInstance")
    server.listen("LaqtaSingleInstance")

    app = LaqtaApp(qapp)

    def on_conn():
        c = server.nextPendingConnection()
        c.waitForReadyRead(300)
        app.show_settings()
    server.newConnection.connect(on_conn)

    if "--open" in sys.argv:  # للتجربة: python laqta.py --open صورة.png
        app.open_file(sys.argv[sys.argv.index("--open") + 1])
    return qapp.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        APP_DIR.mkdir(parents=True, exist_ok=True)
        (APP_DIR / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        if IS_WIN:
            ctypes.windll.user32.MessageBoxW(0, traceback.format_exc()[-1500:], "Laqta - error", 0x10)
        raise
