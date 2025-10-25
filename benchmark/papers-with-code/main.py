import datetime
import tempfile
import subprocess
import os
import typing
import polars
import pathlib
import util
import paper_datasets
import charmonium.cache
import polars_util
import cache_util


print("Started")


seed = 0
# How many of the total to look for citations
sample_size = int(os.environ.get("sample_size", "2000"))

# How many of the top cited to look through for filetypes
sample_size2 = int(os.environ.get("sample_size2", "10"))

n_rows = 10
polars.Config.set_fmt_str_lengths(1000)
polars.Config.set_tbl_rows(n_rows * 5)


domain_regex = r"(?:[a-z]+://)?([A-Za-z0-9_\-\.]+)"
github_regex = r"github.com/+([A-Za-z0-9_\.\-]+)/+([A-Za-z0-9_\.\-]+)"


_T = typing.TypeVar("_T")


def apply_and_return(func: typing.Callable[[_T], None]) -> typing.Callable[[_T], _T]:
    def new_func(item: _T) -> _T:
        func(item)
        return item
    return new_func


@charmonium.cache.memoize(group=cache_util.group)
def analyze_repo(repo_url: str) -> None | typing.Iterable[typing.Mapping[str, str]]:
    tar_file = paper_datasets.download_repo_tarball(repo_url)
    if tar_file is None:
        return []
    else:
        with tar_file as tarfile_obj:
            ret = []
            for member in tarfile_obj.getmembers():
                path_parts = pathlib.Path(member.name).parts[1:]
                if len(path_parts) == 1:
                    filename = path_parts[-1]
                    member = util.tarfile_follow_links(tarfile_obj, member)
                    if member.isdir():
                        ret.append({"name": filename, "type": "inode/directory"})
                    elif member.isfile():
                        file_obj = tarfile_obj.extractfile(member)
                        assert file_obj is not None
                        contents = file_obj.read()
                        type = util.get_file_type_of_bytes(contents)
                        ret.append({"name": filename, "type": type})
                    else:
                        ret.append({"name": filename, "type": "unknown-file-type"})
            return ret


@charmonium.cache.memoize(group=cache_util.group)
def execute_repo(repo_url: str) -> typing.Mapping[str, typing.Any]:
    with paper_datasets.download_repo_tarball(repo_url) as tarfile_obj:
        with tempfile.TemporaryDirectory() as _tmp_dir:
            tmp_dir = pathlib.Path(_tmp_dir)
            tarfile_obj.extractall(tmp_dir)
            start = datetime.datetime.now()
            script = """
            if [ -f src/pyproject.toml ] || [ -f src/setup.py ]; then
                pip install .
            else if [ -f src/requirements.txt ] ; then
                pip install -r src/requirements.txt
            else
                exit 102
            fi"
            """
            proc = subprocess.run(
                ["podman", "run", f"--volume={tmp_dir}:/src:ro", "--rm", "--device=nvidia.com/gpu=all", "--security-opt=label=disable", "runner", script],
                capture_output=True,
                check=False,
            )
            stop = datetime.datetime.now()
    return {
        "returncode": proc.returncode,
        "walltime": (start - stop).total_seconds(),
    }


print()
df = (
    paper_datasets.papers_with_code()
    .pipe(apply_and_return(lambda df: print(
        f"Total: {len(df)} rows\n",
        list(zip(df.columns, df.dtypes)),
        "",
        sep="\n",
    )))

    # Dedup
    # .pipe(apply_and_return(lambda df: print(
    #     "The database contains (paper, repo) edges",
    #     "It is neither unique by papers nor by repos, but almost unique by paper and repos",
    #     "The exceptions appear to be resubmitted papers:",
    #     "For papers that have been submitted multiple times, the URL will be lexicographically greater.",
    #     "E.g., 'https://$thing' > 'https://$thing-1'",
    #     "We'll sort by paper_url, keep the later (longer) URL, and deduplicate by (paper, repo).",
    #     (df
    #         .group_by("paper_url_pdf", "repo_url")
    #         .agg(polars.col("paper_url"), polars.len())
    #         .filter(polars.col("len") > 1)
    #     ),
    #     "",
    #     sep="\n",
    # )))
    .sort(polars.col("paper_url"))
    .with_columns(polars.struct("paper_url_abs", "repo_url").alias("_pair"))
    .unique("_pair", keep="last")
    .drop("_pair")
    .pipe(apply_and_return(lambda df: print(f"Dropping dup papers: {len(df)}\n")))

    # Filter for official
    .filter("is_official")
    .pipe(apply_and_return(lambda df: print(
        f"Filtering for official: {len(df)}\n"
    )))

    # Analyze framework
    .pipe(apply_and_return(lambda df: print(
        "Brekadown by frameworks:",
        df.group_by("framework").len().sort("len", descending=True).head(n_rows),
        "",
        sep="\n",
    )))

    # Find repo hoster
    .with_columns(
        polars.col("repo_url").str.extract(domain_regex, 1).alias("repo_hoster")
    )
    .pipe(apply_and_return(lambda df: print(
        "Brekadown by repo hoster:",
        df.group_by("repo_hoster").len().sort("len", descending=True).head(n_rows),
        "",
        sep="\n",
    )))

    # Parse GitHub data
    .with_columns(
        polars.col("repo_url").str.extract(github_regex, 1).alias("repo_github_owner"),
        polars.col("repo_url").str.extract(github_regex, 2).alias("repo_github_repo"),
    ).with_columns(
        polars.col("repo_hoster").str.to_lowercase().str.contains("github.com").alias("repo_github"),
        (~polars.col("repo_github_owner").is_null() & ~polars.col("repo_github_repo").is_null()).alias("repo_github_parsed"),
    )
    .pipe(apply_and_return(lambda df: print(
        (lambda
         n_parsed=len(df.filter('repo_github_parsed')),
         n_total=len(df.filter('repo_github')):
         f"Parsed {n_parsed} of {n_total}; {n_parsed / n_total*1e4:0.2f}%%\n"
         )(),
    )))
    .filter("repo_github_parsed")
    .drop("repo_github_parsed", "repo_github")

    # Find publisher
    .with_columns(
        polars.col("paper_url_abs").str.extract(domain_regex, 1).alias("paper_publisher"),
    )
    .pipe(apply_and_return(lambda df: print(
        "Brekadown by publishers:",
        df.group_by("paper_publisher").len().sort("len", descending=True).head(n_rows),
        "",
        sep="\n",
    )))

    # Downsample
    .pipe(apply_and_return(lambda df: print(
        f"{len(df)} total, downsampling to {sample_size}, {sample_size / len(df)*1e4:0.2f}%%",
        "Using a deterministic shuffle based on paper_url_abs and repo_url, so the shuffle remains stable.",
        "",
        sep="\n",
    )))
    .pipe(
        polars_util.deterministic_shuffle,
        key=polars.struct("paper_url_abs", "repo_url"),
        seed=seed,
    )
    .head(sample_size)

    # Add GitHub stars
    # .with_columns(
    #     polars_util.map_elements_with_progress(
    #         paper_datasets.count_github_stars,
    #         polars.Int64,
    #         "repo_github_owner",
    #         "repo_github_repo",
    #     ).alias("github_stars")
    # )
    # .pipe(apply_and_return(lambda df: print(
    #     "Sorted by GitHub stars:",
    #     df.sort("github_stars", descending=True).head(n_rows),
    #     "",
    #     sep="\n",
    # )))

    # Add citations
    .with_columns(
        polars_util.map_elements_with_progress(
            paper_datasets.get_arxiv_citations,
            polars.Int64,
            "paper_arxiv_id",
            skip_nulls=True,
        ).alias("citations")
    )
    .pipe(apply_and_return(lambda df: print(
        "Sorted by citations:",
        df.select(
            polars.col("citations").fill_null(0),
            polars.exclude("citations"),
        ).sort("citations", descending=True).head(n_rows),
        "",
        sep="\n",
    )))

    # Only take top cited
    .drop_nulls("citations")
    .pipe(apply_and_return(lambda df: print(
        f"N with citations: {len(df)}",
        "",
        sep="\n",
    )))
    .sort("citations", descending=True)
 
   .head(sample_size2)

    # TODO:
    # How to connect
    # https://arxiv.org/abs/1905.00537
    # to
    # https://papers.nips.cc/paper/8589-superglue-a-stickier-benchmark-for-general-purpose-language-understanding-systems.pdf

    # Most common file types
    # .with_columns(
    #     polars_util.map_elements_with_progress(
    #         analyze_repo,
    #         polars.List(polars.Struct({"name": polars.String, "type": polars.String})),
    #         "repo_url",
    #         skip_nulls=True,
    #     ).alias("repo_files")
    # )
    # .pipe(apply_and_return(lambda df: print(
    #     "Most common file/types:",
    #     df
    #     .explode("repo_files")
    #     .group_by("repo_files")
    #     .len()
    #     .sort("len", descending=True)
    #     .head(n_rows*2),
    #     sep="\n",
    # )))
    # # How many are Pipable
    # .with_row_index()
    # .explode("repo_files")
    # .unnest("repo_files")
    # .with_columns(polars.col("name").is_in({"setup.py", "pyproject.toml", "requirements.txt"}).alias("pipable"))
    # .group_by("index")
    # .agg(
    #     polars.col("pipable").any(),
    #     polars.col("name").alias("filenames"),
    #     polars.col("type").alias("filetypes"),
    #     polars.all().exclude("pipable", "index", "name", "type").first(),
    # )
    # .drop("index")
    # .pipe(apply_and_return(lambda df: print(
    #     "Pipable := has setup.py, pyproject.toml, or requirements.txt",
    #     df.group_by("pipable")
    #     .len()
    #     .sort("pipable", descending=True),
    #     "",
    #     sep="\n",
    # )))

    # Write outputs
    .pipe(apply_and_return(lambda df:
        print(
            "Good candidates",
            (
                df
                .glimpse()
            ),
            sep="\n",
        )
    ))
    .pipe(apply_and_return(lambda df:
        df.write_csv("test.csv")
    ))
)


# try:
#     (df
#     # Try automatic execution
#     # .filter("pipable")
#     # .with_columns(
#     #     polars_util.map_elements_with_progress(
#     #         execute_repo,
#     #         polars.Struct({"returncode": polars.Int64, "walltime": polars.Int64}),
#     #         "repo_url",
#     #     ).alias("execution_status")
#     # )
#     # .unnest("execution_status")
#     # .head(sample_size2)
#     # .pipe(apply_and_return(lambda df: print(
#     #     "successfully installed?",
#     #     df.group_by("returncode").len().sort("len", descending=True),
#     #     "",
#     #     sep="\n",
#     # )))
#      )
# except Exception:
#     print(traceback.format_exc())
#     import IPython; IPython.embed()
