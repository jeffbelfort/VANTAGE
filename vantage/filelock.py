"""Nonblocking process locks on Unix and Windows; lock files are never truncated."""
import os
if os.name == 'nt':
    import msvcrt
    LOCK_EX, LOCK_SH, LOCK_NB, LOCK_UN = 1, 2, 4, 8
    def flock(handle, operation):
        fd = handle if isinstance(handle, int) else handle.fileno()
        os.lseek(fd, 0, os.SEEK_SET)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b'\0')
            os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK if operation & LOCK_UN else msvcrt.LK_NBLCK, 1)
else:
    from fcntl import flock, LOCK_EX, LOCK_SH, LOCK_NB, LOCK_UN
