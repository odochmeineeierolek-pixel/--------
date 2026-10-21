"""Oberfläche (PySide6): Kreis in der Mitte, rot/schwarz/gelb, Tabs für alle Funktionen."""
import math
import os
import random
import sys
import tempfile
import threading
import urllib.request

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QSlider, QSpinBox, QSystemTrayIcon, QMenu, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget, QDialog, QAbstractItemView)

from . import programs, voices
from .assistant import Assistant, Hooks
from .config import home_dir

STYLE = """
QWidget{background:#0a0a0a;color:#f2f2f2;font-family:'Segoe UI';font-size:14px}
QTabWidget::pane{border:1px solid #3a0000}
QTabBar::tab{background:#140000;color:#ffd400;padding:9px 16px;border:1px solid #3a0000}
QTabBar::tab:selected{background:#e10600;color:#000;font-weight:bold}
QPushButton{background:#1a0000;border:1px solid #e10600;color:#ffd400;padding:8px 14px;border-radius:6px}
QPushButton:hover{background:#e10600;color:#000}
QPushButton#stop{background:#e10600;color:#000;font-weight:bold}
QLineEdit,QTextEdit,QPlainTextEdit,QListWidget,QComboBox,QSpinBox{background:#120000;border:1px solid #5a0000;color:#fff;padding:5px;selection-background-color:#ffd400;selection-color:#000}
QSlider::groove:horizontal{height:6px;background:#3a0000}
QSlider::handle:horizontal{background:#ffd400;width:16px;margin:-6px 0;border-radius:8px}
QCheckBox::indicator{width:16px;height:16px}
QLabel#status{color:#ffd400;font-size:15px}
"""

PALETTE = {  # innen, außen, Ringfarbe 1, Ringfarbe 2
    "neutral": ("#ffd400", "#e10600", "#e10600", "#ffd400"),
    "nett": ("#fff07a", "#ff9d00", "#ffd400", "#ff9d00"),
    "boese": ("#ff3300", "#6a0000", "#ff0000", "#a00000"),
    "traurig": ("#8a6a00", "#2a0a0a", "#5a2a00", "#8a6a00"),
}
STATUS_TEXT = {"idle": "Bereit – sag „YAVIS“", "listening": "Ich höre zu …", "thinking": "Ich denke nach …",
               "speaking": "", "muted": "Mikrofon aus", "loading": "Lade Spracherkennung …", "error": "Fehler – siehe Verlauf"}


def make_icon():
    pm = QPixmap(128, 128)
    pm.fill(QColor("#050505"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for r, c in ((56, "#780000"), (44, "#e10600"), (28, "#ffd400")):
        p.setBrush(QColor(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(64, 64), r, r)
    p.end()
    return QIcon(pm)


class Orb(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(340, 340)
        self.state, self.emotion = "idle", "neutral"
        self.level, self.ext, self.t, self.rot = 0.0, 0.0, 0.0, 0.0
        tm = QTimer(self)
        tm.timeout.connect(self._tick)
        tm.start(30)

    def set_ext(self, v):
        self.ext = v

    def _tick(self):
        self.t += 0.03
        speed = {"idle": 0.4, "listening": 0.9, "thinking": 2.4, "speaking": 1.3, "muted": 0.1}.get(self.state, 0.4)
        if self.emotion == "boese":
            speed *= 1.8
        elif self.emotion == "traurig":
            speed *= 0.5
        self.rot = (self.rot + speed * 2) % 360
        if self.state == "speaking":
            target = 0.25 + 0.55 * abs(math.sin(self.t * 7.3)) * (0.6 + 0.4 * random.random())
        elif self.state == "thinking":
            target = 0.15 + 0.1 * math.sin(self.t * 6)
        elif self.state == "muted":
            target = 0.0
        else:
            target = 0.05 + 0.04 * math.sin(self.t * 1.5) + min(0.55, self.ext * 0.9)
        if self.emotion == "traurig":
            target *= 0.6
        self.level += (target - self.level) * 0.35
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#050505"))
        inner, outer, r1, r2 = (QColor(c) for c in PALETTE.get(self.emotion, PALETTE["neutral"]))
        c = QPointF(self.width() / 2, self.height() / 2)
        base = min(self.width(), self.height()) * 0.19
        r = base * (1 + 0.45 * self.level)
        g = QRadialGradient(c, r * 2.6)
        glow = QColor(outer)
        glow.setAlpha(150)
        g.setColorAt(0, glow)
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, r * 2.6, r * 2.6)
        g2 = QRadialGradient(c - QPointF(r * 0.25, r * 0.25), r * 1.25)
        g2.setColorAt(0, inner)
        g2.setColorAt(0.65, outer)
        g2.setColorAt(1, QColor("#120000"))
        p.setBrush(g2)
        p.drawEllipse(c, r, r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, (scale, span, col, w, d) in enumerate(((1.35, 110, r1, 4, 1), (1.6, 70, r2, 3, -1), (1.9, 40, r1, 2, 1))):
            pen = QPen(col, w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            rr = base * scale * (1 + 0.25 * self.level)
            rect = QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr)
            for k in range(3):
                p.drawArc(rect, int((self.rot * d + i * 40 + k * 120) * 16), int(span * 16))


class Bridge(QObject):
    log = Signal(str, str)
    state = Signal(str)
    emotion = Signal(str)
    level = Signal(float)
    notice = Signal(str)
    status = Signal(str)
    confirm = Signal(str, object)
    text_out = Signal(str)


class UiHooks(Hooks):
    def __init__(self, bridge):
        self.b = bridge

    def log(self, role, text): self.b.log.emit(role, text)
    def state(self, s): self.b.state.emit(s)
    def emotion(self, e): self.b.emotion.emit(e)
    def level(self, v): self.b.level.emit(float(v))
    def notice(self, kind): self.b.notice.emit(kind)

    def confirm(self, question):
        holder = {"ok": False, "ev": threading.Event()}
        self.b.confirm.emit(question, holder)
        holder["ev"].wait(90)
        return holder["ok"]


class MainWindow(QMainWindow):
    def __init__(self, start_listener=True):
        super().__init__()
        self.setWindowTitle("YAVIS")
        self.setWindowIcon(make_icon())
        self.resize(1120, 780)
        self.setStyleSheet(STYLE)
        self._quitting = False
        self.b = Bridge()
        self.a = Assistant(UiHooks(self.b))
        self.s = self.a.s
        self.b.log.connect(self.on_log)
        self.b.state.connect(self.on_state)
        self.b.emotion.connect(self.on_emotion)
        self.b.level.connect(lambda v: self.orb.set_ext(v))
        self.b.notice.connect(self.on_notice)
        self.b.status.connect(lambda t: self.status.setText(t))
        self.b.confirm.connect(self.on_confirm)
        self.b.text_out.connect(lambda t: self.sales_out.setPlainText(t))
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        for name, fn in (("Zentrum", self.tab_center), ("Programme", self.tab_programs), ("Musik", self.tab_music),
                         ("Stimme", self.tab_voice), ("Namen", self.tab_names), ("Gedächtnis", self.tab_memory),
                         ("Verkauf", self.tab_sales), ("Einstellungen", self.tab_settings)):
            tabs.addTab(fn(), name)
        self._tray()
        if start_listener:
            if self.s.get("always_listen"):
                self.a.start_listening()
            QTimer.singleShot(1500, lambda: threading.Thread(target=self._check_brain, daemon=True).start())

    # ---------- Tabs ----------
    def tab_center(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.orb = Orb()
        v.addWidget(self.orb, 1)
        self.status = QLabel(STATUS_TEXT["idle"])
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.status)
        row = QHBoxLayout()
        self.btn_mic = QPushButton("🎤 Mikrofon an")
        self.btn_mic.setCheckable(True)
        self.btn_mic.setChecked(True)
        self.btn_mic.toggled.connect(self._mic_toggled)
        b_listen = QPushButton("Jetzt zuhören")
        b_listen.clicked.connect(self.a.activate)
        b_stop = QPushButton("■ STOPP")
        b_stop.setObjectName("stop")
        b_stop.clicked.connect(self.a.stop)
        b_up, b_down = QPushButton("👍"), QPushButton("👎")
        b_up.clicked.connect(lambda: self.a.feedback(True))
        b_down.clicked.connect(self._thumb_down)
        for x in (self.btn_mic, b_listen, b_stop, b_up, b_down):
            row.addWidget(x)
        v.addLayout(row)
        inp = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Oder hier schreiben …")
        self.inp.returnPressed.connect(self._send)
        send = QPushButton("Senden")
        send.clicked.connect(self._send)
        inp.addWidget(self.inp)
        inp.addWidget(send)
        v.addLayout(inp)
        self.chk_text = QCheckBox("Text anzeigen (Standard: nur Sprache)")
        self.chk_text.setChecked(bool(self.s.get("show_text")))
        self.chk_text.toggled.connect(self._text_toggled)
        v.addWidget(self.chk_text)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumHeight(160)
        self.logbox.setVisible(bool(self.s.get("show_text")))
        v.addWidget(self.logbox)
        self._history = []
        return w

    def tab_programs(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Haken = YAVIS darf dieses Programm starten. Alles andere startet er nie."))
        self.plist = QListWidget()
        v.addWidget(self.plist)
        self._fill_programs()
        self.plist.itemChanged.connect(self._save_allowed)
        row = QHBoxLayout()
        for text, fn in (("Alle erlauben", lambda: self._set_all(True)), ("Keine erlauben", lambda: self._set_all(False)),
                         ("Startmenü durchsuchen …", self._scan_menu), ("Datei/Spiel hinzufügen …", self._add_custom),
                         ("Entfernen", self._remove_custom), ("Test-Start", self._test_start)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        return w

    def tab_music(self):
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        self.lbl_folder = QLabel(self.s.get("music_folder") or "Kein Musikordner gewählt")
        b = QPushButton("Musikordner wählen …")
        b.clicked.connect(self._pick_music)
        top.addWidget(self.lbl_folder, 1)
        top.addWidget(b)
        v.addLayout(top)
        self.tracklist = QListWidget()
        self.tracklist.itemDoubleClicked.connect(lambda it: self.a.music.play(self.tracklist.row(it)))
        v.addWidget(self.tracklist)
        row = QHBoxLayout()
        for text, fn in (("⏮", self.a.music.prev), ("▶ Abspielen", lambda: self.a.music.play(self.tracklist.currentRow() if self.tracklist.currentRow() >= 0 else None)),
                         ("⏸", self.a.music.pause), ("⏯ Weiter", self.a.music.resume), ("⏭", self.a.music.next), ("■", self.a.music.stop)):
            bb = QPushButton(text)
            bb.clicked.connect(lambda _=False, f=fn: f())
            row.addWidget(bb)
        v.addLayout(row)
        vol = QSlider(Qt.Orientation.Horizontal)
        vol.setRange(0, 100)
        vol.setValue(int(self.s.get("volume")))
        vol.valueChanged.connect(self.a.music.set_volume)
        v.addWidget(QLabel("Lautstärke (Musik und Stimme)"))
        v.addWidget(vol)
        if self.s.get("music_folder"):
            self._reload_tracks()
        return w

    def tab_voice(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(f"{len(voices.VOICES)} Stimmen-Voreinstellungen (Frau / Mann, warm, samtig, Mama, hart, …)"))
        self.cmb_voice = QComboBox()
        for vo in voices.VOICES:
            self.cmb_voice.addItem(("♀ " if vo.gender == "f" else "♂ ") + vo.label, vo.id)
        self.cmb_voice.setCurrentIndex(max(0, self.cmb_voice.findData(self.s.get("voice"))))
        self.cmb_voice.currentIndexChanged.connect(lambda: self.s.set("voice", self.cmb_voice.currentData()))
        v.addWidget(self.cmb_voice)
        for label, key, lo, hi in (("Tempo (%)", "voice_rate", -40, 40), ("Tonhöhe (Hz)", "voice_pitch", -30, 30)):
            v.addWidget(QLabel(label))
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(int(self.s.get(key)))
            sl.valueChanged.connect(lambda val, k=key: self.s.set(k, val))
            v.addWidget(sl)
        v.addWidget(QLabel("Gefühle"))
        self.cmb_mood = QComboBox()
        for text, key in (("Automatisch (nett / traurig / böse je nach Lage)", "auto"), ("Immer neutral", "neutral"),
                          ("Immer nett & lieb", "nett"), ("Immer böse", "boese"), ("Immer traurig", "traurig")):
            self.cmb_mood.addItem(text, key)
        self.cmb_mood.setCurrentIndex(max(0, self.cmb_mood.findData(self.s.get("mood"))))
        self.cmb_mood.currentIndexChanged.connect(lambda: self.s.set("mood", self.cmb_mood.currentData()))
        v.addWidget(self.cmb_mood)
        off = QCheckBox("Nur Windows-Offline-Stimme verwenden (kein Internet, klingt einfacher)")
        off.setChecked(bool(self.s.get("offline_voice")))
        off.toggled.connect(lambda c: self.s.set("offline_voice", c))
        v.addWidget(off)
        prev = QPushButton("Stimme anhören")
        prev.clicked.connect(lambda: self.a.say(f"Hallo {self.a.title}, so klinge ich. Gefällt dir das?", "nett", log=False))
        v.addWidget(prev)
        v.addStretch(1)
        return w

    def tab_names(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Aktivierungswörter – YAVIS hört auf jedes dieser Wörter (ein Wort, mind. 3 Buchstaben):"))
        self.wlist = QListWidget()
        self.wlist.addItems(self.s.get("wake_words"))
        v.addWidget(self.wlist)
        row = QHBoxLayout()
        self.wedit = QLineEdit()
        self.wedit.setPlaceholderText("Neuer Name …")
        add, rem = QPushButton("Hinzufügen"), QPushButton("Entfernen")
        add.clicked.connect(self._add_wake)
        rem.clicked.connect(self._rem_wake)
        for x in (self.wedit, add, rem):
            row.addWidget(x)
        v.addLayout(row)
        v.addWidget(QLabel("Anrede (Standard: Master):"))
        t = QLineEdit(self.s.get("user_title"))
        t.textChanged.connect(lambda x: self.s.set("user_title", x.strip() or "Master"))
        v.addWidget(t)
        v.addStretch(1)
        return w

    def tab_memory(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.cmb_mem = QComboBox()
        for text, tb in (("Gemerkte Fakten", "facts"), ("Notizen", "notes"), ("Aufgaben", "todos"),
                         ("Feedback / Lektionen", "feedback"), ("Aktionsprotokoll", "actions")):
            self.cmb_mem.addItem(text, tb)
        self.cmb_mem.currentIndexChanged.connect(self._refresh_mem)
        v.addWidget(self.cmb_mem)
        self.mlist = QListWidget()
        self.mlist.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        v.addWidget(self.mlist)
        row = QHBoxLayout()
        for text, fn in (("Neu laden", self._refresh_mem), ("Auswahl löschen", self._del_mem), ("Diese Liste leeren", self._clear_mem),
                         ("ALLES löschen", self._clear_all_mem)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        v.addWidget(QLabel("Gespeichert wird nur, was du sagst („Merk dir …“, „Notiere …“) oder bewertest. Alles bleibt lokal."))
        self._refresh_mem()
        return w

    def tab_sales(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Verkaufshilfe: Texte vorbereiten. Veröffentlichen, Kaufen, Bezahlen, Senden machst du selbst."))
        self.sales_in = QTextEdit()
        self.sales_in.setPlaceholderText("Produktdaten oder Kunde/Leistung eintragen …")
        self.sales_in.setMaximumHeight(130)
        v.addWidget(self.sales_in)
        row = QHBoxLayout()
        for text, tpl in (("Beschreibung erstellen", "Schreibe eine ehrliche, ansprechende Verkaufsbeschreibung (max. 6 Sätze) für:\n{}"),
                          ("Angebot entwerfen", "Entwirf ein höfliches Angebot mit Preis-Platzhaltern für:\n{}"),
                          ("Kleinanzeigen-Titel & Text", "Schreibe einen Titel (max. 60 Zeichen) und einen kurzen Text für eine Kleinanzeige zu:\n{}")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, t=tpl: self._gen(t))
            row.addWidget(b)
        pb = QPushButton("Preise im Browser prüfen")
        pb.clicked.connect(self._prices)
        row.addWidget(pb)
        v.addLayout(row)
        self.sales_out = QTextEdit()
        v.addWidget(self.sales_out, 1)
        return w

    def tab_settings(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Sprachmodell (Ollama, lokal & kostenlos)"))
        self.ed_model = QLineEdit(self.s.get("model"))
        self.ed_model.editingFinished.connect(lambda: self.s.set("model", self.ed_model.text().strip()))
        v.addWidget(self.ed_model)
        row = QHBoxLayout()
        b1, b2, b3 = QPushButton("Ollama installieren"), QPushButton("Modell herunterladen"), QPushButton("Verbindung testen")
        b1.clicked.connect(self._install_ollama)
        b2.clicked.connect(self._pull_model)
        b3.clicked.connect(lambda: threading.Thread(target=self._check_brain, args=(True,), daemon=True).start())
        for x in (b1, b2, b3):
            row.addWidget(x)
        v.addLayout(row)
        v.addWidget(QLabel("Spracherkennung (Whisper-Größe: tiny/base/small/medium – größer = genauer, aber langsamer; Neustart nötig)"))
        cw = QComboBox()
        cw.addItems(["tiny", "base", "small", "medium"])
        cw.setCurrentText(self.s.get("whisper_model"))
        cw.currentTextChanged.connect(lambda t: self.s.set("whisper_model", t))
        v.addWidget(cw)
        al = QCheckBox("Dauerhaft auf Aktivierungswort hören (Mikrofon-Status immer sichtbar)")
        al.setChecked(bool(self.s.get("always_listen")))
        al.toggled.connect(lambda c: self.s.set("always_listen", c))
        v.addWidget(al)
        au = QCheckBox("YAVIS mit Windows starten (im Hintergrund, Tray-Symbol)")
        au.setChecked(self._autostart_get())
        au.toggled.connect(self._autostart_set)
        v.addWidget(au)
        v.addWidget(QLabel(f"Daten liegen lokal in: {home_dir()}"))
        v.addStretch(1)
        return w

    # ---------- Slots ----------
    def on_log(self, role, text):
        who = {"user": "Du", "yavis": "YAVIS", "system": "System"}.get(role, role)
        self.logbox.appendPlainText(f"{who}: {text}")
        if role == "user":
            self.status.setText("„" + text[:70] + "“")

    def on_state(self, s):
        self.orb.state = s
        if s != "speaking":
            self.status.setText(STATUS_TEXT.get(s, ""))

    def on_emotion(self, e):
        self.orb.emotion = e if e in PALETTE else "neutral"

    def on_confirm(self, question, holder):
        r = QMessageBox.question(self, "Bestätigung nötig", question)
        holder["ok"] = r == QMessageBox.StandardButton.Yes
        holder["ev"].set()

    def on_notice(self, kind):
        if kind == "ollama_missing":
            if QMessageBox.question(self, "Ollama fehlt", "Für das lokale KI-Gehirn wird das kostenlose Ollama benötigt. Jetzt herunterladen und installieren?") == QMessageBox.StandardButton.Yes:
                self._install_ollama()
        elif kind == "model_missing":
            if QMessageBox.question(self, "Modell fehlt", f"Das Modell {self.s.get('model')} ist noch nicht geladen (ca. 2 GB, einmalig). Jetzt herunterladen?") == QMessageBox.StandardButton.Yes:
                self._pull_model()

    def _send(self):
        t = self.inp.text().strip()
        if t:
            self.inp.clear()
            self.a.submit(t)

    def _mic_toggled(self, on):
        self.btn_mic.setText("🎤 Mikrofon an" if on else "🔇 Mikrofon aus")
        self.a.set_muted(not on)

    def _text_toggled(self, on):
        self.s.set("show_text", on)
        self.logbox.setVisible(on)

    def _thumb_down(self):
        note, ok = QInputDialog.getText(self, "Was war falsch?", "Kurz sagen, was YAVIS besser machen soll (optional):")
        if ok:
            self.a.feedback(False, note)

    # Programme
    def _fill_programs(self):
        self.plist.blockSignals(True)
        self.plist.clear()
        allowed = programs.allowed_ids(self.s)
        for e in programs.all_entries(self.s):
            it = QListWidgetItem(e.name + ("  (eigenes)" if e.id.startswith("custom:") else ""))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if e.id in allowed else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, e.id)
            self.plist.addItem(it)
        self.plist.blockSignals(False)

    def _save_allowed(self, *_):
        ids = [self.plist.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.plist.count())
               if self.plist.item(i).checkState() == Qt.CheckState.Checked]
        self.s.set("allowed_programs", ids)

    def _set_all(self, on):
        self.plist.blockSignals(True)
        for i in range(self.plist.count()):
            self.plist.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.plist.blockSignals(False)
        self._save_allowed()

    def _add_custom_entry(self, name, path):
        c = self.s.get("custom_programs")
        c[name] = path
        self.s.set("custom_programs", c)
        allowed = list(programs.allowed_ids(self.s)) if self.s.get("allowed_programs") is not None else None
        if allowed is not None:
            allowed.append("custom:" + name)
            self.s.set("allowed_programs", allowed)

    def _add_custom(self):
        path, _ = QFileDialog.getOpenFileName(self, "Programm, Spiel oder Verknüpfung wählen", "", "Alle Dateien (*.*)")
        if path:
            default = os.path.splitext(os.path.basename(path))[0]
            name, ok = QInputDialog.getText(self, "Name", "Wie soll ich es nennen, wenn du es sagst?", text=default)
            if ok and name.strip():
                self._add_custom_entry(name.strip(), path)
                self._fill_programs()

    def _scan_menu(self):
        found = programs.scan_start_menu(force=True)
        if not found:
            QMessageBox.information(self, "Startmenü", "Keine Verknüpfungen gefunden (nur unter Windows).")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Programme aus dem Startmenü hinzufügen")
        dlg.resize(460, 560)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lst.addItems(sorted(found, key=str.lower))
        lay.addWidget(lst)
        ok = QPushButton("Ausgewählte hinzufügen")
        ok.clicked.connect(dlg.accept)
        lay.addWidget(ok)
        if dlg.exec():
            for it in lst.selectedItems():
                self._add_custom_entry(it.text(), found[it.text()])
            self._fill_programs()

    def _remove_custom(self):
        it = self.plist.currentItem()
        if it and it.data(Qt.ItemDataRole.UserRole).startswith("custom:"):
            name = it.data(Qt.ItemDataRole.UserRole)[7:]
            c = self.s.get("custom_programs")
            c.pop(name, None)
            self.s.set("custom_programs", c)
            self._fill_programs()

    def _test_start(self):
        it = self.plist.currentItem()
        if it:
            pid = it.data(Qt.ItemDataRole.UserRole)
            e = next((x for x in programs.all_entries(self.s) if x.id == pid), None)
            ok, msg = programs.launch(e)
            if not ok:
                QMessageBox.warning(self, "Start", msg)

    # Musik
    def _pick_music(self):
        d = QFileDialog.getExistingDirectory(self, "Musikordner wählen")
        if d:
            self.s.set("music_folder", d)
            self.lbl_folder.setText(d)
            self._reload_tracks()

    def _reload_tracks(self):
        n = self.a.music.load_folder(self.s.get("music_folder"))
        self.tracklist.clear()
        self.tracklist.addItems([p.stem for p in self.a.music.tracks])
        self.lbl_folder.setText(f"{self.s.get('music_folder')}  ({n} Titel)")

    # Namen
    def _add_wake(self):
        w = self.wedit.text().strip().lower()
        if len(w) >= 3 and " " not in w and w not in self.s.get("wake_words"):
            self.s.set("wake_words", self.s.get("wake_words") + [w])
            self.wlist.addItem(w)
            self.wedit.clear()

    def _rem_wake(self):
        it = self.wlist.currentItem()
        words = self.s.get("wake_words")
        if it and len(words) > 1:
            words.remove(it.text())
            self.s.set("wake_words", words)
            self.wlist.takeItem(self.wlist.row(it))

    # Gedächtnis
    def _refresh_mem(self, *_):
        self.mlist.clear()
        for i, text, extra in self.a.mem.list(self.cmb_mem.currentData()):
            it = QListWidgetItem(text + ("  ✓" if self.cmb_mem.currentData() == "todos" and extra else ""))
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.mlist.addItem(it)

    def _del_mem(self):
        for it in self.mlist.selectedItems():
            self.a.mem.delete(self.cmb_mem.currentData(), it.data(Qt.ItemDataRole.UserRole))
        self._refresh_mem()

    def _clear_mem(self):
        if QMessageBox.question(self, "Löschen", "Diese Liste komplett leeren?") == QMessageBox.StandardButton.Yes:
            self.a.mem.clear(self.cmb_mem.currentData())
            self._refresh_mem()

    def _clear_all_mem(self):
        if QMessageBox.question(self, "ALLES löschen", "Wirklich ALLE gespeicherten Daten löschen?") == QMessageBox.StandardButton.Yes:
            self.a.mem.clear()
            self._refresh_mem()

    # Verkauf
    def _gen(self, tpl):
        txt = self.sales_in.toPlainText().strip()
        if not txt:
            return
        self.sales_out.setPlainText("Ich schreibe …")
        threading.Thread(target=lambda: self.b.text_out.emit(self.a.generate_text(tpl.format(txt))), daemon=True).start()

    def _prices(self):
        txt = self.sales_in.toPlainText().strip().split("\n")[0]
        if txt:
            self.a.submit("preise " + txt)

    # Ollama
    def _check_brain(self, verbose=False):
        if not self.a.brain.available():
            self.b.notice.emit("ollama_missing")
        elif not self.a.brain.has_model():
            self.b.notice.emit("model_missing")
        else:
            threading.Thread(target=self.a.brain.warmup, daemon=True).start()
            if verbose:
                self.b.status.emit("Ollama läuft, Modell bereit.")

    def _install_ollama(self):
        def work():
            try:
                self.b.status.emit("Lade Ollama herunter …")
                dest = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
                urllib.request.urlretrieve("https://ollama.com/download/OllamaSetup.exe", dest)
                self.b.status.emit("Ollama-Installer gestartet. Danach hier „Modell herunterladen“ drücken.")
                os.startfile(dest)  # noqa
            except Exception as ex:
                self.b.status.emit(f"Download fehlgeschlagen: {ex}")
        threading.Thread(target=work, daemon=True).start()

    def _pull_model(self):
        def work():
            try:
                self.a.brain.pull(self.s.get("model"), lambda st, pct: self.b.status.emit(f"Modell: {st} {pct if pct is not None else ''}{'%' if pct is not None else ''}"))
                self.b.status.emit("Modell fertig geladen.")
                self.a.brain.available()
                self.a.brain.warmup()
            except Exception as ex:
                self.b.status.emit(f"Modell-Download fehlgeschlagen (läuft Ollama?): {ex}")
        threading.Thread(target=work, daemon=True).start()

    # Autostart & Tray
    @staticmethod
    def _autostart_get():
        if os.name != "nt":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, "YAVIS")
                return True
        except Exception:
            return False

    @staticmethod
    def _autostart_set(on):
        if os.name != "nt":
            return
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
            if on:
                cmd = f'"{sys.executable}" --minimized' if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" --minimized'
                winreg.SetValueEx(k, "YAVIS", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, "YAVIS")
                except FileNotFoundError:
                    pass

    def _tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        m = QMenu()
        a1, a2 = QAction("YAVIS öffnen"), QAction("Beenden")
        a1.triggered.connect(self.showNormal)
        a2.triggered.connect(self._quit)
        m.addAction(a1)
        m.addAction(a2)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.showNormal() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.setToolTip("YAVIS läuft – sag „YAVIS“")
        self.tray.show()

    def _quit(self):
        self._quitting = True
        self.a.music.stop()
        self.a.speaker.stop()
        if self.a.listener:
            self.a.listener.stop()
        QApplication.quit()

    def closeEvent(self, e):
        if self._quitting or not self.tray.isVisible():
            e.accept()
        else:
            e.ignore()
            self.hide()
            self.tray.showMessage("YAVIS", "Läuft im Hintergrund weiter. Rechtsklick auf das Symbol zum Beenden.")
