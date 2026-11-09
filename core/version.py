"""Program version and comparison with GitHub release tags.

Tags look like V1.1.6a, V1.2.0, V1.2.0-Beta3. Before, the About tab could
not parse its own "V1.1.6a" (int("V1") fails), fell back to "different
means newer" and offered every other tag as an update - including older
ones (a beta was asked to "update" to the previous release).

Python 3.8 compatible. No Qt.
"""
import re

APP_VERSION = "V2.0.0-dev"

# pre-release words, lowest first; a final release is above all of them
_PRE = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "rc": 3, "pre": 3}
_RX = re.compile(r"^\s*[vV]?\s*(\d+(?:\.\d+)*)\s*[-_.]?\s*([A-Za-z]*)\s*\.?(\d*)\s*$")


def parse(version):
    """(numbers, pre) or None. pre is None for a final release, else
    (rank, number): "1.2.0-Beta3" -> ((1, 2, 0), (2, 3))."""
    m = _RX.match(str(version or ""))
    if not m:
        return None
    nums = tuple(int(x) for x in m.group(1).split("."))
    word = m.group(2).lower()
    if not word:
        return nums, None
    if word not in _PRE:
        return None
    return nums, (_PRE[word], int(m.group(3) or 0))


def _key(parsed, width):
    nums, pre = parsed
    nums = nums + (0,) * (width - len(nums))
    # final release (pre None) sorts after every pre-release of the same numbers
    return nums, (1, 0, 0) if pre is None else (0,) + pre


def is_newer(latest, current):
    """Is `latest` (a release tag) newer than `current`? Unparseable -> False:
    better no prompt than a wrong one."""
    a, b = parse(latest), parse(current)
    if a is None or b is None:
        return False
    width = max(len(a[0]), len(b[0]))
    return _key(a, width) > _key(b, width)
