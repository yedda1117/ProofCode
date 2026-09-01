import json
import tempfile
import unittest
from pathlib import Path

from proofcode.trajectory import TrajectoryRecorder


class TrajectoryRecorderTests(unittest.TestCase):
    def test_writes_ordered_jsonl_events(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            recorder = TrajectoryRecorder.create(Path(directory))

            recorder("run_started", {"task": "修复测试"})
            recorder("run_finished", {"reason": "completed"})

            records = [
                json.loads(line)
                for line in recorder.path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([item["event"] for item in records], ["run_started", "run_finished"])
            self.assertEqual(records[0]["data"]["task"], "修复测试")
            self.assertTrue(all(item["run_id"] == recorder.run_id for item in records))

    def test_creates_separate_files_for_runs(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            first = TrajectoryRecorder.create(Path(directory))
            second = TrajectoryRecorder.create(Path(directory))

            self.assertNotEqual(first.path, second.path)
            self.assertEqual(first.path.parent, second.path.parent)


if __name__ == "__main__":
    unittest.main()
