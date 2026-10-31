"""Fault-injected publication invariants; no process or native runtime."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from uav_tracking import stop_observer as m


class PublicationFixture(unittest.TestCase):
    def make(self,directory):
        return m.StopObserver(directory/'events.jsonl',directory/'summary.json')

    def test_summary_fsync_failure_leaves_only_unpublished_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);observer=self.make(directory)
            real_fsync=m.os.fsync;calls=[]
            def fsync(fd):
                calls.append(fd)
                if len(calls)==2:
                    raise OSError('summary-only fsync failed')
                return real_fsync(fd)
            with patch.object(m.os,'fsync',side_effect=fsync):
                result=observer.close()
            self.assertEqual(result['status'],'EVIDENCE_INCOMPLETE')
            self.assertFalse(observer.summary_path.exists())
            self.assertEqual(len(list(directory.glob('summary.json.partial.*'))),1)

    def test_link_failure_does_not_publish_complete_final_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);observer=self.make(directory)
            with patch.object(m.os,'link',side_effect=OSError('exclusive publication failed')):
                result=observer.close()
            self.assertEqual(result['status'],'EVIDENCE_INCOMPLETE')
            self.assertFalse(observer.summary_path.exists())
            self.assertEqual(len(list(directory.glob('summary.json.partial.*'))),1)

    def test_final_name_created_by_another_actor_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);observer=self.make(directory)
            original=b'{"status":"preexisting evidence"}'
            observer.summary_path.write_bytes(original)
            result=observer.close()
            self.assertEqual(result['status'],'EVIDENCE_INCOMPLETE')
            self.assertEqual(observer.summary_path.read_bytes(),original)
            self.assertEqual(len(list(directory.glob('summary.json.partial.*'))),1)

    def test_postpublication_partial_unlink_failure_preserves_complete_durable_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);observer=self.make(directory);real_unlink=Path.unlink
            def unlink(path,*args,**kwargs):
                if '.partial.' in path.name:
                    raise OSError('staging link retained')
                return real_unlink(path,*args,**kwargs)
            with patch.object(Path,'unlink',new=unlink):
                result=observer.close()
            self.assertEqual(result['status'],'EVIDENCE_COMPLETE')
            self.assertEqual(json.loads(observer.summary_path.read_text())['status'],'EVIDENCE_COMPLETE')
            partials=list(directory.glob('summary.json.partial.*'))
            self.assertEqual(len(partials),1)
            self.assertEqual(partials[0].read_bytes(),observer.summary_path.read_bytes())

    def test_successful_publication_removes_staging_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);observer=self.make(directory);result=observer.close()
            self.assertEqual(result['status'],'EVIDENCE_COMPLETE')
            self.assertEqual(json.loads(observer.summary_path.read_text()),result)
            self.assertEqual(list(directory.glob('summary.json.partial.*')),[])


if __name__=='__main__':
    unittest.main(verbosity=2)
