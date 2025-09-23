
import sys
import os
import time
import wave
import threading
import tempfile
import subprocess
import shlex
import shutil
from pathlib import Path
from typing import Callable, Optional, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QListWidget, QTabWidget, QFileDialog,
    QFormLayout, QSpinBox, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QObject


def write_wav_from_pcm(pcm_bytes: bytes, out_path: str, sample_rate: int, channels: int, sampwidth: int):
    with wave.open(out_path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

def run_panako_query(java_bin: str, panako_jar: str, wav_path: str, extra_java_args: Optional[List[str]] = None, timeout=30):
    cmd = [java_bin]
    if extra_java_args:
        cmd += extra_java_args
    cmd += ['-jar', panako_jar, 'query', wav_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (result.stdout or '') + (result.stderr or '')
        return result.returncode, out
    except subprocess.TimeoutExpired:
        return 124, 'PANAKO QUERY TIMEOUT'

def monitor_stream_loop(stream_url: str, songs_dir: str, panako_jar: str,
                        java_bin='java', ffmpeg_bin='ffmpeg',
                        sample_rate=44100, channels=1, sampwidth=2,
                        window_seconds=25, overlap_seconds=5,
                        add_opens: Optional[List[str]] = None,
                        miss_threshold: int = 2,
                        on_line: Callable[[str], None] = lambda s: None,
                        stop_event: threading.Event = None):
    """Blocking monitor loop. Call in a background thread. Uses callbacks for output lines."""
    if stop_event is None:
        stop_event = threading.Event()

    extra_java_args = []
    if add_opens:
        for ao in add_opens:
            extra_java_args += ['--add-opens', ao]

    step_seconds = window_seconds - overlap_seconds
    bytes_per_second = sample_rate * channels * sampwidth
    window_bytes = window_seconds * bytes_per_second

    songs = []
    for p in Path(songs_dir).glob('**/*.mp3'):
        songs.append(p.name)
    if not songs:
        on_line(f"Warning: no MP3s found in {songs_dir}")
    song_tokens = [s.lower() for s in songs]

    ffmpeg_cmd = [
        ffmpeg_bin, '-i', stream_url,
        '-vn',
        '-ac', str(channels),
        '-ar', str(sample_rate),
        '-f', 's16le',
        '-'
    ]
    on_line('Starting ffmpeg: ' + ' '.join(shlex.quote(s) for s in ffmpeg_cmd))
    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception as e:
        on_line(f"[FFMPEG ERROR] {e}")
        return

    if proc.stdout is None:
        on_line("[FFMPEG ERROR] stdout not captured")
        return

    buffer = bytearray()
    last_check = time.time()
    active = {}
    check_count = 0

    try:
        while not stop_event.is_set():
            chunk = proc.stdout.read(bytes_per_second // 4)
            if not chunk:
                on_line("ffmpeg ended or no data, exiting")
                break
            buffer += chunk
            if len(buffer) > window_bytes:
                del buffer[0: len(buffer) - window_bytes]

            now = time.time()
            if now - last_check >= step_seconds:
                last_check = now
                check_count += 1
                on_line(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] Running query #{check_count} (window {window_seconds}s)')

                with tempfile.NamedTemporaryFile(prefix='panako_q_', suffix='.wav', delete=False) as tf:
                    tmpwav = tf.name
                try:
                    write_wav_from_pcm(bytes(buffer), tmpwav, sample_rate, channels, sampwidth)
                    rc, out = run_panako_query(java_bin, panako_jar, tmpwav, extra_java_args=extra_java_args, timeout=40)
                    out_low = (out or '').lower()

                    matched_tokens = set()
                    for token, orig in zip(song_tokens, songs):
                        if token in out_low:
                            matched_tokens.add(orig)

                    current_seen = set()
                    if matched_tokens:
                        for songname in matched_tokens:
                            current_seen.add(songname)
                            if songname not in active:
                                active[songname] = {'last_seen': check_count, 'miss_count': 0}
                                on_line(f"DETECTED: {songname} (check #{check_count})")
                            else:
                                active[songname]['last_seen'] = check_count
                                active[songname]['miss_count'] = 0
                                on_line(f"DETECTED (still): {songname} (check #{check_count})")

                    for songname in list(active.keys()):
                        if songname not in current_seen:
                            active[songname]['miss_count'] += 1
                            if active[songname]['miss_count'] >= miss_threshold:
                                on_line(f"ENDED: {songname} (last seen check #{active[songname]['last_seen']})")
                                del active[songname]
                finally:
                    try:
                        os.unlink(tmpwav)
                    except Exception:
                        pass

    except KeyboardInterrupt:
        on_line('Keyboard interrupt, stopping')
    except Exception as e:
        on_line(f"[MONITOR ERROR] {e}")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        on_line("[MONITOR STOPPED]")


DEFAULT_ADD_OPENS = [
    "java.base/java.nio=ALL-UNNAMED",
    "java.base/java.lang=ALL-UNNAMED"
]

def run_store_for_songs(java_bin: str, panako_jar: str, songs_dir: str, db_dir: Optional[str],
                        add_opens: Optional[List[str]] = None,
                        on_line: Callable[[str], None] = lambda s: None,
                        stop_event: threading.Event = None):
    """
    Run Panako 'store' on all mp3 files under songs_dir, one file at a time.
    Streams stdout/stderr lines to on_line callback.

    This avoids shell pipelines and accidental directory arguments.
    """
    if stop_event is None:
        stop_event = threading.Event()

    used_add_opens = add_opens or DEFAULT_ADD_OPENS

    extra_java_args = []
    for ao in used_add_opens:
        extra_java_args += ['--add-opens', ao]

    files = sorted(Path(songs_dir).glob('**/*.mp3'))
    if not files:
        on_line(f"[FINGERPRINT] No .mp3 files found in {songs_dir}")
        return

    total = len(files)
    on_line(f"[FINGERPRINT] Found {total} mp3 files")

    dbpath_str = None
    if db_dir:
        try:
            dbp = Path(db_dir).expanduser().resolve()
            dbp.mkdir(parents=True, exist_ok=True)
            dbpath_str = str(dbp)
            on_line(f"[FINGERPRINT] Using DB dir: {dbpath_str}")
        except Exception as e:
            on_line(f"[FINGERPRINT ERROR] Could not create/prepare DB dir '{db_dir}': {e}")
            dbpath_str = None

    for idx, p in enumerate(files, start=1):
        if stop_event.is_set():
            on_line("[FINGERPRINT] Stop requested, exiting")
            break

        fpath = str(p)
        on_line(f"[FINGERPRINT] ({idx}/{total}) Processing: {fpath}")

        cmd = [java_bin] + extra_java_args + ['-jar', str(panako_jar), 'store', '-f', fpath]
        if dbpath_str:
            cmd += ['-d', dbpath_str]

        on_line("[FINGERPRINT] CMD: " + " ".join(shlex.quote(x) for x in cmd))

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except Exception as e:
            on_line(f"[FINGERPRINT ERROR] failed to start java for {fpath}: {e}")
            continue

        try:
            if proc.stdout:
                for line in proc.stdout:
                    if stop_event.is_set():
                        break
                    on_line(line.rstrip('\n'))
            rc = proc.wait()
            on_line(f"[FINGERPRINT] process exit {rc} for {fpath}")
        except Exception as e:
            on_line(f"[FINGERPRINT ERROR] {e}")
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

    on_line("[FINGERPRINT STOPPED]")


class GuiSignals(QObject):
    line = Signal(str)

class MonitorThread(threading.Thread):
    def __init__(self, *, target, targs=(), tkwargs=None):
        if not callable(target):
            raise ValueError("MonitorThread requires a callable 'target' argument")
        super().__init__(daemon=True)
        self._target = target
        self._targs = tuple(targs)
        self._tkwargs = dict(tkwargs or {})
        self.stop_event = threading.Event()
        self.signals = GuiSignals()

    def run(self):
        try:
            def on_line(s: str):
                try:
                    self.signals.line.emit(s)
                except Exception:
                    print("Failed to emit signal:", s, file=sys.stderr)

            if 'stop_event' not in self._tkwargs:
                self._tkwargs['stop_event'] = self.stop_event
            if 'on_line' not in self._tkwargs:
                self._tkwargs['on_line'] = on_line
            self._target(*self._targs, **self._tkwargs)

        except Exception as e:
            try:
                self.signals.line.emit(f"[THREAD ERROR] {repr(e)}")
            except Exception:
                print("[THREAD ERROR]", repr(e), file=sys.stderr)
        finally:
            try:
                self.signals.line.emit("[THREAD FINISHED]")
            except Exception:
                pass

    def stop(self):
        self.stop_event.set()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Panako Stream Monitor (local paths default)")
        self.resize(1000, 700)

        self.script_dir = Path(__file__).resolve().parent
        self.default_jar = self.script_dir / 'panako-2.1-all.jar'
        self.default_songs = self.script_dir / 'songs'
        self.default_db = self.script_dir / 'panako_db'

        tabs = QTabWidget()
        tabs.addTab(self._setup_tab(), "Setup")
        tabs.addTab(self._fingerprint_tab(), "Fingerprint")
        tabs.addTab(self._monitor_tab(), "Monitor")
        tabs.addTab(self._logs_tab(), "Logs")
        self.setCentralWidget(tabs)

        self.monitor_thread: Optional[MonitorThread] = None
        self.fingerprint_thread: Optional[MonitorThread] = None

    def _setup_tab(self):
        w = QWidget()
        form = QFormLayout()

        self.edit_jar = QLineEdit(str(self.default_jar))
        btn_jar = QPushButton("Browse")
        btn_jar.clicked.connect(self._browse_jar)
        hjar = QHBoxLayout(); hjar.addWidget(self.edit_jar); hjar.addWidget(btn_jar)

        self.edit_songs = QLineEdit(str(self.default_songs))
        btn_songs = QPushButton("Browse")
        btn_songs.clicked.connect(self._browse_songs)
        hs = QHBoxLayout(); hs.addWidget(self.edit_songs); hs.addWidget(btn_songs)

        self.edit_db = QLineEdit(str(self.default_db))
        btn_db = QPushButton("Browse")
        btn_db.clicked.connect(self._browse_db)
        hd = QHBoxLayout(); hd.addWidget(self.edit_db); hd.addWidget(btn_db)

        self.edit_java = QLineEdit("java")
        self.edit_ffmpeg = QLineEdit("ffmpeg")

        self.spin_window = QSpinBox(); self.spin_window.setValue(25); self.spin_window.setRange(5,120)
        self.spin_overlap = QSpinBox(); self.spin_overlap.setValue(5); self.spin_overlap.setRange(0,60)
        self.spin_sr = QSpinBox(); self.spin_sr.setValue(44100); self.spin_sr.setRange(8000,192000)
        self.spin_channels = QSpinBox(); self.spin_channels.setValue(1); self.spin_channels.setRange(1,2)
        self.spin_miss = QSpinBox(); self.spin_miss.setValue(2); self.spin_miss.setRange(1,10)

        self.edit_add_opens = QLineEdit("java.base/java.nio=ALL-UNNAMED java.base/java.lang=ALL-UNNAMED")

        form.addRow("Panako JAR (default next to script):", hjar)
        form.addRow("Songs folder (default ./songs):", hs)
        form.addRow("Panako DB folder (optional):", hd)
        form.addRow("java binary:", self.edit_java)
        form.addRow("ffmpeg binary:", self.edit_ffmpeg)
        form.addRow("Window seconds:", self.spin_window)
        form.addRow("Overlap seconds:", self.spin_overlap)
        form.addRow("Sample rate:", self.spin_sr)
        form.addRow("Channels:", self.spin_channels)
        form.addRow("Miss threshold:", self.spin_miss)
        form.addRow("Extra --add-opens (space-separated):", self.edit_add_opens)

        note = QLabel("Note: Panako prints 'Skipped: resource already stored' for files it already indexed.")
        note.setWordWrap(True)
        form.addRow(note)

        w.setLayout(form)
        return w

    def _fingerprint_tab(self):
        w = QWidget()
        v = QVBoxLayout()

        h = QHBoxLayout()
        self.btn_start_fp = QPushButton("Start Fingerprinting (store)")
        self.btn_stop_fp = QPushButton("Stop Fingerprinting")
        self.chk_force = QCheckBox("Force reindex (delete DB folder before storing)")
        self.chk_show_skipped_only = QCheckBox("Only show summary (don't append every line to GUI)")
        self.btn_start_fp.clicked.connect(self.start_fingerprinting)
        self.btn_stop_fp.clicked.connect(self.stop_fingerprinting)
        self.btn_stop_fp.setEnabled(False)
        h.addWidget(self.btn_start_fp); h.addWidget(self.btn_stop_fp); h.addWidget(self.chk_force); h.addWidget(self.chk_show_skipped_only)
        v.addLayout(h)

        self.fp_output = QTextEdit()
        self.fp_output.setReadOnly(True)
        v.addWidget(self.fp_output)

        w.setLayout(v)
        return w

    def _monitor_tab(self):
        w = QWidget()
        v = QVBoxLayout()

        h = QHBoxLayout()
        self.edit_stream = QLineEdit("")
        h.addWidget(QLabel("Stream URL:"))
        h.addWidget(self.edit_stream)
        v.addLayout(h)

        h2 = QHBoxLayout()
        self.btn_start = QPushButton("Start Monitor")
        self.btn_stop = QPushButton("Stop Monitor")
        self.btn_status = QLabel("")
        self.btn_start.clicked.connect(self.start_monitor)
        self.btn_stop.clicked.connect(self.stop_monitor)
        self.btn_stop.setEnabled(False)
        h2.addWidget(self.btn_start); h2.addWidget(self.btn_stop); h2.addWidget(self.btn_status)
        v.addLayout(h2)

        v.addWidget(QLabel("Detections:"))
        self.list_detect = QListWidget()
        v.addWidget(self.list_detect)

        w.setLayout(v)
        return w

    def _logs_tab(self):
        w = QWidget()
        v = QVBoxLayout()
        self.text_logs = QTextEdit()
        self.text_logs.setReadOnly(True)
        v.addWidget(self.text_logs)
        w.setLayout(v)
        return w

    def _browse_jar(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select panako JAR", str(self.script_dir))
        if p: self.edit_jar.setText(p)
    def _browse_songs(self):
        p = QFileDialog.getExistingDirectory(self, "Select songs folder", str(self.script_dir))
        if p: self.edit_songs.setText(p)
    def _browse_db(self):
        p = QFileDialog.getExistingDirectory(self, "Select DB folder", str(self.script_dir))
        if p: self.edit_db.setText(p)

    def _append_log(self, txt: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        self.text_logs.append(f"[{ts}] {txt}")

    def _on_line(self, line: str):
        if 'DETECTED:' in line or 'DETECTED (still):' in line or 'ENDED:' in line:
            self.list_detect.addItem(line)
        self._append_log(line)


    def start_monitor(self):
        try:
            running = getattr(self, 'monitor_thread', None)
            if running is not None and running.is_alive():
                QMessageBox.warning(self, "Already running", "Monitor already running")
                return
        except Exception:
            self.monitor_thread = None

        stream = self.edit_stream.text().strip()
        if not stream:
            QMessageBox.critical(self, "Error", "Provide stream URL")
            return

        jar = self.edit_jar.text().strip()
        songs = self.edit_songs.text().strip()
        java_bin = self.edit_java.text().strip() or "java"
        ffmpeg_bin = self.edit_ffmpeg.text().strip() or "ffmpeg"

        if not Path(jar).exists():
            QMessageBox.critical(self, "Error", f"Panako jar not found: {jar}")
            return
        if not Path(songs).exists():
            QMessageBox.critical(self, "Error", f"Songs folder not found: {songs}")
            return

        window = int(self.spin_window.value())
        overlap = int(self.spin_overlap.value())
        sr = int(self.spin_sr.value())
        channels = int(self.spin_channels.value())
        miss = int(self.spin_miss.value())
        add_opens = [x for x in (self.edit_add_opens.text().strip().split()) if x] or DEFAULT_ADD_OPENS

        try:
            self.monitor_thread = MonitorThread(
                target=monitor_stream_loop,
                targs=(stream, songs, jar),
                tkwargs={
                    'java_bin': java_bin,
                    'ffmpeg_bin': ffmpeg_bin,
                    'sample_rate': sr,
                    'channels': channels,
                    'sampwidth': 2,
                    'window_seconds': window,
                    'overlap_seconds': overlap,
                    'add_opens': add_opens,
                    'miss_threshold': miss
                }
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create monitor thread: {e}")
            return

        self.monitor_thread.signals.line.connect(self._on_line)
        self.monitor_thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_status.setText("Running")

    def stop_monitor(self):
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.btn_status.setText("Stopping...")
            self.btn_stop.setEnabled(False)


    def start_fingerprinting(self):
        try:
            running = getattr(self, 'fingerprint_thread', None)
            if running is not None and running.is_alive():
                QMessageBox.warning(self, "Already running", "Fingerprinting already running")
                return
        except Exception:
            self.fingerprint_thread = None

        jar = self.edit_jar.text().strip()
        songs = self.edit_songs.text().strip()
        dbdir = self.edit_db.text().strip() or None
        java_bin = self.edit_java.text().strip() or "java"
        add_opens = [x for x in (self.edit_add_opens.text().strip().split()) if x] or DEFAULT_ADD_OPENS
        force = self.chk_force.isChecked()
        only_summary = self.chk_show_skipped_only.isChecked()

        if not Path(jar).exists():
            QMessageBox.critical(self, "Error", f"Panako jar not found: {jar}")
            return
        if not Path(songs).exists():
            QMessageBox.critical(self, "Error", f"Songs folder not found: {songs}")
            return

        if force and dbdir:
            dbp = Path(dbdir)
            if dbp.exists():
                ok = QMessageBox.question(self, "Confirm delete DB", f"Force reindex will DELETE the DB folder:\n{dbdir}\n\nThis is destructive and irreversible. Continue?", QMessageBox.Yes | QMessageBox.No)
                if ok == QMessageBox.Yes:
                    try:
                        shutil.rmtree(dbp)
                        self._append_log(f"[FINGERPRINT] Deleted DB folder {dbdir} (force)")
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to delete DB folder: {e}")
                        return
                else:
                    self._append_log("[FINGERPRINT] Force reindex cancelled by user")
                    return

        self.fp_output.clear()

        def on_fp_line(line: str):
            low = (line or '').lower()
            if not only_summary:
                self.fp_output.append(line)
            self._append_log("[FP] " + line)

        try:
            self.fingerprint_thread = MonitorThread(
                target=run_store_for_songs,
                targs=(java_bin, jar, songs, dbdir),
                tkwargs={
                    'add_opens': add_opens,
                }
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create fingerprint thread: {e}")
            return

        self.fingerprint_thread.signals.line.connect(on_fp_line)
        self.fingerprint_thread.start()

        self.btn_start_fp.setEnabled(False)
        self.btn_stop_fp.setEnabled(True)

    def stop_fingerprinting(self):
        if self.fingerprint_thread:
            self.fingerprint_thread.stop()
            self.btn_stop_fp.setEnabled(False)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
