"""Native desktop GUI for the provenance scrubber (PySide6).

    python desktop_gui.py

Drag files/folders in or use the pickers, choose a level, optionally attach
detector plugins, run. Processing happens on a worker thread; the table fills
in live. A JSON report can be exported afterwards.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from scrubber.analyzer import analyze, pretty
from scrubber.pipeline import iter_images, process
from scrubber.plugins import load_plugins

LEVEL_LABELS = [
    "0 — metadata strip only (lossless, pixel-identical)",
    "1 — clean re-encode (q97)",
    "2 — q90 + resample + faint noise",
    "3 — aggressive (micro-crop, jitter, q88)",
]


class Worker(QThread):
    progressed = Signal(int, int, str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, src, out_dir, level, detectors):
        super().__init__()
        self.src, self.out_dir, self.level, self.detectors = (
            src, out_dir, level, detectors)

    def run(self):
        try:
            results = process(
                self.src, self.out_dir, level=self.level,
                detectors=self.detectors,
                progress=lambda d, t, r: self.progressed.emit(
                    d, t, Path(r.source).name))
            self.finished_ok.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Provenance Scrubber")
        self.resize(980, 640)
        self.results = []

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        # --- source / destination rows
        row = QHBoxLayout()
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("Source: image file or folder…")
        b_src_f = QPushButton("File…")
        b_src_d = QPushButton("Folder…")
        b_src_f.clicked.connect(self.pick_file)
        b_src_d.clicked.connect(self.pick_folder)
        row.addWidget(QLabel("Source:"))
        row.addWidget(self.src_edit, 1)
        row.addWidget(b_src_f)
        row.addWidget(b_src_d)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        self.out_edit = QLineEdit("scrubbed")
        b_out = QPushButton("Browse…")
        b_out.clicked.connect(self.pick_out)
        row2.addWidget(QLabel("Output:"))
        row2.addWidget(self.out_edit, 1)
        row2.addWidget(b_out)
        lay.addLayout(row2)

        # --- options row
        row3 = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItems(LEVEL_LABELS)
        self.det_meta = QCheckBox("metadata detector")
        self.det_meta.setChecked(True)
        self.det_shell = QLineEdit()
        self.det_shell.setPlaceholderText(
            "optional: external detector command, use {path} (e.g. "
            "/opt/lab/aidec --json {path})")
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self.run)
        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.clicked.connect(self.do_analyze)
        row3.addWidget(QLabel("Level:"))
        row3.addWidget(self.level)
        row3.addWidget(self.det_meta)
        row3.addWidget(self.det_shell, 1)
        row3.addWidget(self.analyze_btn)
        row3.addWidget(self.run_btn)
        lay.addLayout(row3)

        # --- progress + table + detail viewer
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["file", "findings before", "after", "PSNR dB", "detectors",
             "status"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText(
            "Select a row for its before/after provenance, or click Analyze "
            "to view what's inside the source.")

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setSizes([400, 220])
        lay.addWidget(split, 1)

        self.table.itemSelectionChanged.connect(self.on_selection)

        self.setAcceptDrops(True)

        row4 = QHBoxLayout()
        self.status = QLabel("Ready.")
        b_export = QPushButton("Export report…")
        b_export.clicked.connect(self.export_report)
        row4.addWidget(self.status, 1)
        row4.addWidget(b_export)
        lay.addLayout(row4)

        self.setAcceptDrops(True)

    # ---------- drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.src_edit.setText(urls[0].toLocalFile())

    # ---------- pickers
    def pick_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp)")
        if p:
            self.src_edit.setText(p)

    def pick_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Choose folder")
        if p:
            self.src_edit.setText(p)

    def pick_out(self):
        p = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if p:
            self.out_edit.setText(p)

    # ---------- provenance viewer
    def do_analyze(self):
        src = self.src_edit.text().strip()
        if not src or not Path(src).exists():
            QMessageBox.warning(self, "Provenance Scrubber",
                                "Choose a valid source file or folder.")
            return
        parts = []
        for img in iter_images(Path(src)):
            parts.append(pretty(analyze(img)))
        self.detail.setPlainText("\n\n".join(parts))
        self.status.setText(f"Provenance analyzed for {len(parts)} file(s)")

    def on_selection(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not self.results:
            return
        idx = rows[0].row()
        if idx >= len(self.results):
            return
        r = self.results[idx]
        lines = [f"File: {Path(r.source).name}"]
        lines.append("--- BEFORE (present in source) ---")
        bef = r.provenance_before
        for m in (bef.get("manifests") or []):
            gen = (m.get("claim_generator", "") + " " +
                   m.get("claim_generator_version", "")).strip()
            lines.append(f"  manifest: {gen}" if gen else "  manifest: (unnamed)")
            for a in (m.get("actions") or []):
                dst = a.get("digital_source_type", "").split("/")[-1]
                sa = a.get("software_agent", "")
                lines.append(f"    action {a.get('action','')}"
                             + (f" by {sa}" if sa else "")
                             + (f" [{dst}]" if dst else ""))
            if m.get("signature_subject"):
                iss = m.get("signature_issuer", "")
                lines.append(f"    signer: {m['signature_subject']}"
                             + (f" (issuer {iss})" if iss else ""))
            if m.get("instance_id"):
                lines.append(f"    instanceID: {m['instance_id']}")
        if not bef.get("has_manifest") and not bef.get("exif") and \
                not bef.get("xmp") and not bef.get("iptc_present"):
            lines.append("  (no provenance metadata)")
        lines.append("")
        lines.append("--- AFTER excision ---")
        aft = r.provenance_after
        if not (aft.get("manifests") or aft.get("exif") or aft.get("xmp")
                or aft.get("iptc_present")):
            lines.append("  (no provenance metadata)")
        else:
            for m in (aft.get("manifests") or []):
                lines.append(f"  manifest: {m.get('claim_generator','')}")
        lines.append("")
        lines.append("--- DIFF (proof) ---")
        d = r.provenance_diff
        if d.get("removed"):
            lines.append("  removed: " + ", ".join(d["removed"]))
        else:
            lines.append("  removed: (none)")
        if d.get("remained"):
            lines.append("  remained: " + ", ".join(d["remained"]))
        else:
            lines.append("  remained: (none)")
        self.detail.setPlainText("\n".join(lines))

    # ---------- run
    def run(self):
        src = self.src_edit.text().strip()
        if not src or not Path(src).exists():
            QMessageBox.warning(self, "Provenance Scrubber",
                                "Choose a valid source file or folder.")
            return
        specs = []
        if self.det_meta.isChecked():
            specs.append("metadata")
        if self.det_shell.text().strip():
            specs.append(f"shell:{self.det_shell.text().strip()}")
        detectors = load_plugins(specs=specs) if specs else None

        total = len(iter_images(Path(src)))
        self.progress.setVisible(True)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.table.setRowCount(0)
        self.run_btn.setEnabled(False)
        self.status.setText(f"Processing {total} file(s)…")

        self.worker = Worker(src, self.out_edit.text().strip(),
                             self.level.currentIndex(), detectors)
        self.worker.progressed.connect(self.on_progress)
        self.worker.finished_ok.connect(self.on_done)
        self.worker.failed.connect(self.on_fail)
        self.worker.start()

    def on_progress(self, done, total, name):
        self.progress.setValue(done)
        self.status.setText(f"[{done}/{total}] {name}")

    def on_done(self, results):
        self.results = results
        self.run_btn.setEnabled(True)
        self.status.setText(
            f"Done: {sum(1 for r in results if r.status == 'ok')} ok, "
            f"{sum(1 for r in results if r.status != 'ok')} error(s).")
        self.table.setRowCount(len(results))
        for i, r in enumerate(results):
            det = " ".join(
                f"{v['plugin']}:"
                + ("FLAG" if v["flagged"] is True else
                   "ok" if v["flagged"] is False else "?")
                for v in r.detector_verdicts)
            cells = [
                Path(r.source).name,
                str(len(r.findings_before)),
                str(len(r.findings_after)),
                "∞" if r.psnr_db is None else f"{r.psnr_db:.1f}",
                det,
                r.status if r.status == "ok" else f"ERROR: {r.error}",
            ]
            for j, val in enumerate(cells):
                self.table.setItem(i, j, QTableWidgetItem(val))

    def on_fail(self, msg):
        self.run_btn.setEnabled(True)
        self.status.setText("Failed.")
        QMessageBox.critical(self, "Provenance Scrubber", msg)

    def export_report(self):
        if not self.results:
            QMessageBox.information(self, "Provenance Scrubber",
                                    "Nothing to export yet.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export report",
                                           "report.json", "JSON (*.json)")
        if p:
            Path(p).write_text(json.dumps(
                [asdict(r) for r in self.results], indent=2))
            self.status.setText(f"Report written to {p}")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
