import httpx
import os
import bitmath
import logging
import charmonium.cache


logger = logging.getLogger("charmonium.cache.ops")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler("cache.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(message)s"))
for handler in logger.handlers:
    logger.removeHandler(handler)
logger.addHandler(fh)
logger.debug(f"pid {os.getpid()}")

logger = logging.getLogger("charmonium.freeze")
logger.setLevel(logging.DEBUG)
fh2 = logging.FileHandler("freeze.log")
fh2.setLevel(logging.DEBUG)
fh2.setFormatter(logging.Formatter("%(message)s"))
for handler in logger.handlers:
    logger.removeHandler(handler)
logger.addHandler(fh2)
logger.debug(f"pid {os.getpid()}")


group = charmonium.cache.MemoizedGroup(
    size=bitmath.GiB(1.0),
    fine_grain_persistence=False,
)


@charmonium.cache.memoize(group=group)
def download(url: str) -> bytes:
    return httpx.get(url, follow_redirects=True).content


@charmonium.cache.memoize(group=group)
def is_url_dereferenceable(url: str) -> bool:
    return httpx.get(url, follow_redirects=True).status_code == 200
