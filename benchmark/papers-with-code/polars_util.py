import tqdm
import typing
import polars


def deterministic_shuffle(
        frame: polars.DataFrame,
        key: polars.Expr | str,
        seed: int = 0,
) -> polars.DataFrame:
    if isinstance(key, str):
        key = polars.col(key)
    return frame.with_columns(
        key.hash(seed).alias("_index")
    ).sort("_index").drop("_index")


def map_elements_with_progress(
        func: typing.Callable[..., typing.Any],
        return_dtype: type[polars.DataType],
        *cols: polars.Expr | str,
        skip_nulls: bool = False,
        **kwargs: typing.Any,
) -> polars.Expr:
    return (
        polars.struct(cols)
        .map_batches(
            lambda rows: polars.Series([
                func(*row.values()) if not skip_nulls or all(elem is not None for elem in row.values()) else None
                for row in tqdm.tqdm(rows, **kwargs)
            ]),
            return_dtype=return_dtype,
        )
    )
