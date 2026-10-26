import logging,os
from logging.handlers import RotatingFileHandler
from pathlib import Path

def configure(root):
 path=Path(os.environ.get('VANTAGE_LOG_DIR') or Path(root)/'data')/'vantage.log';path.parent.mkdir(parents=True,exist_ok=True)
 handler=RotatingFileHandler(path,maxBytes=2*1024*1024,backupCount=3);handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
 logger=logging.getLogger();logger.setLevel(logging.INFO);logger.addHandler(handler)
