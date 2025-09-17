import dataclasses
import typing
import typing_extensions


FuncParams = typing_extensions.ParamSpec("FuncParams")
FuncReturn = typing.TypeVar("FuncReturn")


cache_path = pathlib.Path(".cache/")
if not cache_path.exists():
    cache_path.mkdir()


@dataclasses.dataclass
class Memoized(typing.Generic[FuncParams, FuncReturn]):
    func: typing.Callable[FuncParams, FuncReturn]
    extra_dependencies: typing.Any = None

    def __call__(
        self, *args: FuncParams.args, **kwargs: FuncParams.kwargs
    ) -> FuncReturn:
        pass
