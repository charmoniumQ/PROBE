from typing import Any, TypeVar
from collections.abc import Mapping, Sequence
import numpy
import numpy.typing


_T = TypeVar("_T")


def kalibera_perf(
        data: numpy.typing.NDArray[numpy.float64],
        cost: numpy.typing.NDArray[numpy.float64],
) -> Mapping[str, numpy.typing.NDArray[numpy.float64]]:
    """See [Kalibera and Jones 2020] for a description of the method
    and variable names. I used the exact same variable names and
    meanings, *except* it simplifies the implementation to use
    0-index instead of 1-index.

    Increasing indices increase specificity. i.e., a[i, j, k, ..., n]
    are iid runs for all n, but not for all i. This is the opposite of
    the paper, but it makes more sense to me.

    [Kalibera and Jones 2020]: https://arxiv.org/abs/2007.10899v1

    """

    n = numpy.array(data.shape)
    Y = data.T
    c = cost[::-1]

    S_squared = numpy.zeros(len(n))
    for i in range(0, len(n)):
        S_squared[i] = Y.mean(axis=tuple(range(i))).var(axis=0, ddof=1).mean()

    T_squared = numpy.zeros(len(n))
    T_squared[0] = S_squared[0]
    T_squared[1:] = S_squared[1:] - S_squared[:-1] / n[::-1][:-1]

    suggested_n = numpy.zeros(len(n) - 1)
    suggested_n[0] = numpy.ceil(numpy.sqrt(c[0] * T_squared[0] / T_squared[1]))
    suggested_n[1:] = numpy.ceil(numpy.sqrt(c[1:-2] * T_squared[1:-1] / c[0:-3] / T_squared[2:]))

    return {
        "biased variance per level": S_squared[::-1],
        "unbiased variance per level": T_squared[::-1],
        "suggested repetitions per level": suggested_n[::-1],
    }
