"""O Monitor SB3 fornece episode como objeto; o CSV precisa de ID numérico."""

import csv
import tempfile
import unittest
from pathlib import Path

from semaforos.experimentos.rl import ProgressCallback


class TrainingEpisodeReportTest(unittest.TestCase):
    def test_monitor_metadata_does_not_replace_episode_number(self):
        with tempfile.TemporaryDirectory() as folder:
            callback = ProgressCallback(folder)
            callback.num_timesteps = 120
            callback.locals = {"infos": [{"unfinished": 2, "simulated_seconds": 600,
                                          "signals": {"tls": {}},
                                          "episode": {"r": -12.5, "l": 120, "t": 4}}]}
            self.assertTrue(callback._on_step())
            with (Path(folder) / "training_episodes.csv").open(newline="", encoding="utf-8") as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row["episode"], "1")
            self.assertEqual(float(row["reward"]), -12.5)
            self.assertNotIn("signals", row)


if __name__ == "__main__":
    unittest.main()
