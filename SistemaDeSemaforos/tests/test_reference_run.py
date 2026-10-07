"""A referência da rede deve executar o programa original sem regravá-lo."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semaforos.simulacao.execucao import run


class ReferenceRunTest(unittest.TestCase):
    def test_default_run_does_not_apply_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with patch("semaforos.simulacao.execucao.load_scenario", return_value=(None, None, {})), \
                 patch("semaforos.simulacao.execucao.simulate", return_value={"score": 0}) as simulate:
                run({"seeds": [11]}, output)
        self.assertIsNone(simulate.call_args.args[3])


if __name__ == "__main__":
    unittest.main()
