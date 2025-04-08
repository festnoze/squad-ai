import sys
from UI_select_dataset_QA import QADatasetSelector

sys.tracebacklimit = 3

QADatasetSelector.init_session()
QADatasetSelector.run(sys.argv)