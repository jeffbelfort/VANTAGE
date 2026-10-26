"""Bounded development backup retention. Never follows symlinks or deletes live files."""
from pathlib import Path

AUTOMATIC_BACKUP_LIMIT=256*1024*1024

def prune_backups(directory,keep=2,max_bytes=2*1024**3):
 directory=Path(directory);files=sorted((p for p in directory.glob('vantage-*.sqlite') if p.is_file() and not p.is_symlink()),reverse=True);retained=0;total=0;removed=[]
 for index,path in enumerate(files):
  size=path.stat().st_size
  # An explicit backup remains usable even when one database exceeds the budget.
  if index==0 or retained<keep and total+size<=max_bytes:
   retained+=1;total+=size;continue
  path.unlink();removed.append(path.name)
 return removed
