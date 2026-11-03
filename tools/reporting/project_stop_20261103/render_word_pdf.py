"""Render only the new report in a private Word instance; preserve user documents."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

runtime = Path(tempfile.gettempdir()) / 'uav_report_20261103_pywin32'
for directory in [runtime, runtime/'win32', runtime/'win32/lib', runtime/'pywin32_system32']:
    sys.path.insert(0, str(directory))
if (runtime/'pywin32_system32').exists():
    os.add_dll_directory(str(runtime/'pywin32_system32'))
import pythoncom
import win32api
import win32com.client
import win32process

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'docs/project-overview-20261103'
docx = OUT/'项目整体报告_20261103.docx'
pdf = OUT/'项目整体报告_20261103.pdf'
receipt = OUT/'word_pdf_render.json'
if pdf.exists() or receipt.exists():
    raise SystemExit('Preserve existing rendered output; choose a fresh report target.')
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before_docx = digest(docx)
before_pids = set(win32process.EnumProcesses())
app = None
document = None
private_instance = False
pythoncom.CoInitialize()
try:
    app = win32com.client.DispatchEx('Word.Application')
    if app.Documents.Count != 0:
        raise RuntimeError('New Word instance contains other documents; refuse to touch it.')
    app.Visible = False
    app.DisplayAlerts = 0
    app.AutomationSecurity = 3
    document = app.Documents.Open(str(docx), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False)
    # Word exposes Hwnd on its document Window, unlike Excel.Application.Hwnd.
    hwnd = document.Windows.Item(1).Hwnd
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid in before_pids or app.Documents.Count != 1 or Path(document.FullName) != docx:
        raise RuntimeError('Private Word process/document identity not established.')
    private_instance = True
    document.Repaginate()
    document.Fields.Update()
    pages = document.ComputeStatistics(2)
    document.ExportAsFixedFormat(str(pdf), 17)
    assert pdf.stat().st_size > 1000 and digest(docx) == before_docx
    record = {'kind':'ACTUAL_PRIVATE_WORD_REPORT_RENDER_NOT_EXPERIMENT',
              'created_utc':datetime.now(timezone.utc).isoformat(),
              'input':{'path':docx.name,'sha256':before_docx},
              'output':{'path':pdf.name,'sha256':digest(pdf),'bytes':pdf.stat().st_size},
              'renderer':{'name':'Microsoft Word','version':str(app.Version),
                          'private_process_confirmed':True,'pid':pid,'document_window_hwnd':hwnd},
              'word_pages':pages,'input_saved_or_changed':False,
              'visual_review':'PENDING'}
    receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(record,ensure_ascii=False))
finally:
    if document is not None:
        document.Close(0)
    if app is not None and private_instance:
        app.Quit(0)
    document = app = None
    pythoncom.CoUninitialize()
