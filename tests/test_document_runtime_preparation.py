"""Private download/archive and Word path fixtures; no real extraction or GUI."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("private_document_runtime", ROOT / "scripts/prepare_document_node24.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class DocumentRuntimePreparationTests(unittest.TestCase):
    def test_official_manifest_requires_exact_unique_filename_and_hash(self):
        text = "a" * 64 + "  " + runtime.ARCHIVE + "\n"
        self.assertEqual(runtime.official_digest(text), "a" * 64)
        for bad in ("missing", text + text, "a" * 63 + "  " + runtime.ARCHIVE):
            with self.assertRaises(ValueError):
                runtime.official_digest(bad)

    def test_download_only_checks_official_digest_and_never_extracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache, tools = root / "private_cache", root / "private_tools"
            payload = b"EXPLICIT_SYNTHETIC_ARCHIVE_BYTES_NOT_A_RUNTIME"
            digest = runtime.hashlib.sha256(payload).hexdigest()
            calls = []
            def fake_download(url, destination, **_):
                calls.append(url)
                Path(destination).write_bytes((digest + "  " + runtime.ARCHIVE + "\n").encode() if str(url).endswith(".txt") else payload)
            with patch.object(runtime.sys, "platform", "linux"), patch.object(runtime.platform, "machine", return_value="x86_64"), patch.object(runtime, "download", side_effect=fake_download):
                result = runtime.prepare(cache, tools)
                self.assertEqual(result["status"], "DOWNLOADED_VERIFIED_NOT_EXTRACTED")
                self.assertFalse(tools.exists())
                self.assertEqual(len(calls), 2)
                self.assertEqual(runtime.prepare(cache, tools), result)
                self.assertEqual(len(calls), 2)
                (cache / runtime.ARCHIVE).write_bytes(b"CHANGED")
                with self.assertRaisesRegex(ValueError, "SHASUMS"):
                    runtime.prepare(cache, tools)

    def test_private_paths_reject_shared_cache_install_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for tools in (path, path / "nested"):
                with self.assertRaises(ValueError):
                    runtime.private_paths(path, tools)

    def test_archive_members_and_links_cannot_leave_node_directory(self):
        prefix = runtime.ARCHIVE.removesuffix(".tar.xz")
        with tempfile.TemporaryDirectory() as directory:
            valid = tarfile.TarInfo(prefix + "/bin/node")
            self.assertEqual(runtime.safe_members(SimpleNamespace(getmembers=lambda: [valid]), directory), [valid])
            for name in ("../outside", prefix + "/../outside", "/absolute"):
                item = tarfile.TarInfo(name)
                with self.assertRaises(ValueError):
                    runtime.safe_members(SimpleNamespace(getmembers=lambda: [item]), directory)
            link = tarfile.TarInfo(prefix + "/bin/unsafe")
            link.type, link.linkname = tarfile.SYMTYPE, "../../../outside"
            with self.assertRaises(ValueError):
                runtime.safe_members(SimpleNamespace(getmembers=lambda: [link]), directory)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell path-only fixture")
    def test_word_script_paths_only_never_starts_word_and_preserves_existing_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "FIXTURE_ONLY.docx", root / "output.pdf"
            source.write_bytes(b"PATH_ONLY_FIXTURE_NOT_A_WORD_DOCUMENT")
            command = [shutil.which("powershell"), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                       str(ROOT / "scripts/convert_v4_word_to_pdf.ps1"), "-InputDocx", str(source), "-OutputPdf", str(output), "-ValidatePathsOnly"]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("NO_WORD_STARTED", result.stdout)
            self.assertFalse(output.exists())
            output.write_bytes(b"KEEP_EXISTING")
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"KEEP_EXISTING")


if __name__ == "__main__":
    unittest.main()
