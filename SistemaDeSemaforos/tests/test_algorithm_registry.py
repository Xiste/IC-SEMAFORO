"""Concurrent Streamlit sessions must share one builtin registration."""

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from semaforos.algoritmos import registro


class AlgorithmRegistryTest(unittest.TestCase):
    def test_concurrent_initialization_and_reruns(self):
        saved = registro._ALGORITHMS.copy()
        registro._ALGORITHMS.clear()
        original = registro.register_algorithm
        start = Barrier(8)

        def delayed_register(algorithm):
            time.sleep(0.02)
            original(algorithm)

        def open_session(_):
            start.wait(timeout=10)
            return registro.available_algorithms()

        try:
            with patch.object(registro, "register_algorithm", delayed_register):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(open_session, range(8)))
            self.assertEqual(results, [["A2C", "PPO"]] * 8)
            self.assertEqual(registro.available_algorithms(), ["A2C", "PPO"])
            with self.assertRaises(ValueError):
                registro.register_algorithm(registro.get_algorithm("PPO"))
        finally:
            registro._ALGORITHMS.clear()
            registro._ALGORITHMS.update(saved)


if __name__ == "__main__":
    unittest.main()
