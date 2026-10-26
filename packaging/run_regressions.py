"""Run only synthetic-profile release regressions; never open historical save evidence."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tests'))
sys.path.insert(0,str(ROOT))
SKIP={'test_original_both_worlds_balance_preservation'}
def flatten(suite):
 for test in suite:
  if isinstance(test,unittest.TestSuite):yield from flatten(test)
  elif test._testMethodName not in SKIP:yield test
suite=unittest.TestSuite()
for module in ('test_player_banking','test_ma','test_fund_settlement','test_qt_runtime'):
 suite.addTests(flatten(unittest.defaultTestLoader.loadTestsFromName(module)))
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
