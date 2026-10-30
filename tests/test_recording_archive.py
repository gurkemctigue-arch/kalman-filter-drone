from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from uav_tracking.recording_archive import (
    RecordingArchiveError, finalize_recording, validate_sqlite_recording, verify_native_reader,
)


def recording(base):
    trial = base / "result"
    trial.mkdir()
    spool = base / "uav_tracking_bag_spool/trial_test"
    spool.mkdir(parents=True)
    (spool / "owned_spool.json").write_text(json.dumps({"trial": str(trial.resolve())}))
    bag = spool / "rosbag"
    bag.mkdir()
    db = sqlite3.connect(bag / "recording.db3")
    db.executescript("CREATE TABLE topics(id INTEGER PRIMARY KEY,name TEXT);"
                     "CREATE TABLE messages(id INTEGER PRIMARY KEY,topic_id INTEGER,timestamp INTEGER,data BLOB);")
    db.executemany("INSERT INTO topics VALUES(?,?)", [(1,"/clock"),(2,"/pose"),(3,"/empty")])
    db.executemany("INSERT INTO messages VALUES(?,?,?,?)",
                   [(1,1,100,b"clock1"),(2,2,110,b"pose"),(3,1,120,b"clock2")])
    db.commit(); db.close()
    info = {"version":5,"storage_identifier":"sqlite3","compression_format":"","compression_mode":"NONE",
            "relative_file_paths":["recording.db3"],"message_count":3,
            "topics_with_message_count":[{"topic_metadata":{"name":name},"message_count":count}
                                         for name,count in (("/clock",2),("/pose",1),("/empty",0))],
            "files":[{"path":"recording.db3","message_count":3}]}
    (bag / "metadata.yaml").write_text(yaml.safe_dump({"rosbag2_bagfile_information":info}))
    return trial, spool, bag


class Rows:
    def __init__(self, topics): self.rows = iter(topics); self.pending = None
    def has_next(self):
        self.pending = next(self.rows, None)
        return self.pending is not None
    def read_next(self): return self.pending,b"not-deserialized",0


class RecordingIntegrityTests(unittest.TestCase):
    def test_reads_all_sqlite_pages_and_keeps_zero_count_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,_,bag=recording(Path(tmp))
            result=validate_sqlite_recording(bag)
            self.assertEqual(result["message_count"],3)
            self.assertEqual(result["topic_counts"],{"/clock":2,"/pose":1,"/empty":0})
            self.assertEqual(result["files"][0]["sqlite_integrity"],"ok")

    def test_missing_rows_are_rejected_even_with_correct_total_metadata_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,_,bag=recording(Path(tmp))
            db=sqlite3.connect(bag/"recording.db3")
            db.execute("DELETE FROM messages WHERE id=3");db.commit();db.close()
            with self.assertRaisesRegex(RecordingArchiveError,"counts"):
                validate_sqlite_recording(bag)

    def test_unknown_topic_and_unclosed_wal_are_rejected(self):
        for defect in ("unknown_topic","wal"):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
                _,_,bag=recording(Path(tmp))
                if defect=="wal":(bag/"recording.db3-wal").write_bytes(b"pending transaction")
                else:
                    db=sqlite3.connect(bag/"recording.db3")
                    db.execute("UPDATE messages SET topic_id=99 WHERE id=1");db.commit();db.close()
                with self.assertRaises(RecordingArchiveError):validate_sqlite_recording(bag)

    def test_bad_sqlite_and_metadata_path_escape_fail_without_repair(self):
        for defect in ("bad_sqlite","escape"):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
                _,_,bag=recording(Path(tmp))
                if defect=="bad_sqlite":(bag/"recording.db3").write_bytes(b"not sqlite")
                else:
                    metadata=yaml.safe_load((bag/"metadata.yaml").read_text())
                    metadata["rosbag2_bagfile_information"]["relative_file_paths"]=["../outside.db3"]
                    (bag/"metadata.yaml").write_text(yaml.safe_dump(metadata))
                before=(bag/"recording.db3").read_bytes()
                with self.assertRaises((sqlite3.Error,RecordingArchiveError)):validate_sqlite_recording(bag)
                self.assertEqual((bag/"recording.db3").read_bytes(),before)

    def test_nonzero_recorder_exit_retains_spool_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial,spool,_=recording(Path(tmp))
            with self.assertRaisesRegex(RecordingArchiveError,"close"):
                finalize_recording(spool,trial/"rosbag",-9)
            self.assertTrue(spool.is_dir());self.assertFalse((trial/"rosbag").exists())

    def test_native_full_stream_missing_or_additional_rows_are_rejected(self):
        expected={"message_count":3,"topic_counts":{"/clock":2,"/pose":1,"/empty":0}}
        for rows in (("/clock","/pose"),("/clock","/clock","/pose","/other")):
            with self.subTest(rows=rows),self.assertRaises(RecordingArchiveError):
                verify_native_reader(Path("unused"),expected,lambda _:Rows(rows))
        result=verify_native_reader(Path("unused"),expected,lambda _:Rows(("/clock","/clock","/pose")))
        self.assertTrue(result["full_stream_read"])

    @unittest.skipUnless(shutil.which("zstd"),"Standard zstd CLI integration runs in the prepared Linux environment")
    def test_standard_zstd_archive_publishes_only_after_byte_and_reader_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial,spool,bag=recording(Path(tmp))
            original=(bag/"recording.db3").read_bytes()
            def reader(stage):
                compressed=stage/"recording.db3.zstd"
                raw=subprocess.check_output(["zstd","-d","-c","-q",str(compressed)])
                self.assertEqual(raw,original)
                return Rows(("/clock","/pose","/clock"))
            with patch("uav_tracking.recording_archive.subprocess.run", wraps=subprocess.run) as run:
                result=finalize_recording(spool,trial/"rosbag",0,reader)
            self.assertEqual(result["status"],"PASS")
            self.assertFalse(spool.exists())
            archive=trial/"rosbag"
            self.assertEqual(sorted(p.name for p in archive.iterdir()),["metadata.yaml","recording.db3.zstd"])
            self.assertEqual(subprocess.check_output(["zstd","-d","-c","-q",str(archive/"recording.db3.zstd")]),original)
            metadata=yaml.safe_load((archive/"metadata.yaml").read_text())["rosbag2_bagfile_information"]
            self.assertEqual(metadata["relative_file_paths"],["recording.db3.zstd"])
            self.assertEqual(result["compressed_files"][0]["raw_sha256"],hashlib.sha256(original).hexdigest())
            compressed=result["compressed_files"][0]
            actual_command=run.call_args_list[0].args[0]
            self.assertEqual(actual_command[:5],["zstd","-T1","-19","--long=27","--check"])
            self.assertEqual(compressed["compression_command"],actual_command)
            self.assertEqual(result["compression_profile"]["arguments"],actual_command[1:5])
            self.assertGreaterEqual(compressed["compression_wall_s"],0.)
            self.assertGreaterEqual(result["archive_processing"]["wall_s"],compressed["compression_wall_s"])
            self.assertIn("closed_recording",result["archive_processing"]["scope"])

    @unittest.skipUnless(shutil.which("zstd"),"Standard zstd CLI integration runs in the prepared Linux environment")
    def test_reader_failure_retains_raw_and_compressed_artifacts_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial,spool,bag=recording(Path(tmp))
            with self.assertRaises(RecordingArchiveError):
                finalize_recording(spool,trial/"rosbag",0,lambda _:Rows(("/clock",)))
            self.assertTrue((bag/"recording.db3").is_file())
            self.assertTrue((spool/"archive/recording.db3.zstd").is_file())
            self.assertFalse((trial/"rosbag").exists())


if __name__=="__main__":unittest.main()
