import charmonium.time_block as ch_tb
import shutil
import hashlib
import os
import yaml  # type: ignore
import pathlib
import subprocess
import re
import urllib.parse
import json
from collections.abc import Sequence, Mapping
from pathlib import Path
from typing import cast
from util import env_command, run_all, CmdArg, check_returncode


result_bin = Path(__file__).resolve().parent / "result/bin"
result_lib = result_bin.parent / "lib"


class Workload:
    kind: str
    name: str

    def setup(self, workdir: Path) -> None:
        pass

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        return ["true"], {"PATH": str(result_bin)}

    def __str__(self) -> str:
        return self.name


class SpackInstall(Workload):
    kind = "compilation"

    def __init__(self, specs: list[str], version: str = "v0.20.1") -> None:
        self.name = "compile " + "+".join(specs)
        self._version = version
        self._env_dir: Path | None = None
        self._specs = specs
        self._env_vars: Mapping[str, str | Path] = {}

    def setup(self, workdir: Path) -> None:
        self._env_vars = {
            "PATH": result_bin,
            "SPACK_USER_CACHE_PATH": workdir,
            "SPACK_USER_CONFIG_PATH": workdir,
            "LD_LIBRARY_PATH": result_lib,
            "LIBRARY_PATH": result_lib,
        }

        # Install spack
        spack_dir = workdir / "spack"
        if not spack_dir.exists():
            check_returncode(subprocess.run(
                run_all(
                    (
                        result_bin / "git", "clone", "-c", "feature.manyFiles=true",
                        "https://github.com/spack/spack.git", spack_dir,
                    ),
                    (
                        result_bin / "git", "-C", spack_dir, "checkout",
                        self._version, "--force",
                    ),
                ),
                env=self._env_vars,
                check=False,
                capture_output=True,
            ), env=self._env_vars)
        spack = spack_dir / "bin" / "spack"
        assert spack.exists()

        # Concretize env with desired specs
        env_name = urllib.parse.quote("-".join(self._specs), safe="")
        if len(env_name) > 64:
            env_name = hashlib.sha256(env_name.encode()).hexdigest()[:16]
        env_dir = workdir / "spack_envs" / env_name
        if not env_dir.exists():
            env_dir.mkdir(parents=True)
            check_returncode(subprocess.run(
                [spack, "env", "create", "--dir", env_dir],
                env=self._env_vars,
                check=False,
                capture_output=True,
            ), env=self._env_vars)
        conf_obj = yaml.safe_load((env_dir / "spack.yaml").read_text())
        conf_obj["spack"]["compilers"][0]["compiler"]["environment"].setdefault("prepend_path", {})["LIBRARY_PATH"] = str(result_lib)
        (env_dir / "spack.yaml").write_text(yaml.dump(conf_obj))
        exports = check_returncode(subprocess.run(
            [spack, "env", "activate", "--sh", "--dir", env_dir],
            env=self._env_vars,
            check=False,
            text=True,
            capture_output=True,
        ), env=self._env_vars).stdout
        pattern = re.compile("^export ([a-zA-Z0-9_]+)=(.*?);?$", flags=re.MULTILINE)
        self._env_vars ={
            **self._env_vars,
            **{
                match.group(1): match.group(2)
                for match in pattern.finditer(exports)
            },
        }
        proc = check_returncode(subprocess.run(
            [spack, "add", *self._specs],
            env=self._env_vars,
            check=False,
            capture_output=True,
        ), env=self._env_vars)
        spec_shorthand = ", ".join(spec.partition("@")[0] for spec in self._specs)
        if not (env_dir / "spack.lock").exists():
            with ch_tb.ctx(f"concretize {spec_shorthand}"):
                check_returncode(subprocess.run(
                    [spack, "concretize"],
                    env=self._env_vars,
                    check=False,
                    capture_output=True,
                ), env=self._env_vars)
        with \
             (env_dir / "spack_install_stdout").open("wb") as stdout, \
             (env_dir / "spack_install_stderr").open("wb") as stderr, \
             ch_tb.ctx(f"install {spec_shorthand}"):
            print(f"`tail --follow {env_dir}/spack_install_stdout` to check progress. Same applies to stderr")
            proc = check_returncode(subprocess.run(
                [spack, "install"],
                env=self._env_vars,
                check=False,
                stdout=stdout,
                stderr=stderr,
            ), env=self._env_vars)

        # Find deps of that env and take out specs we asked for
        with ch_tb.ctx("get deps"):
            script = "; ".join([
                "import spack.environment",
                f"env = spack.environment.Environment('{env_dir}')",
                "print('\\n'.join(map(str, set(env.all_specs()))))",
            ])
            dependency_specs = list(filter(bool, check_returncode(subprocess.run(
                (spack, "python", "-c", script),
                env=self._env_vars,
                check=False,
                capture_output=True,
                text=True,
            ), env=self._env_vars).stdout.strip().split("\n")))

            generalized_specs = [
                spec.partition("@")[0]
                for spec in self._specs
            ]
            direct_dependency_specs = [
                spec
                for spec in dependency_specs
                if spec.partition("@")[0] in generalized_specs
            ]
            indirect_dependency_specs = [
                spec
                for spec in dependency_specs
                if spec.partition("@")[0] not in generalized_specs
            ]

        # Create mirror with source code of self._specs
        name = "env_mirror"
        mirror_dir = env_dir / name
        mirrors = check_returncode(subprocess.run(
            (spack, "mirror", "list"),
            env=self._env_vars,
            check=False,
            capture_output=True,
            text=True,
        ), env=self._env_vars).stdout
        if name not in mirrors:
            with ch_tb.ctx(f"create mirror {name}"):
                if mirror_dir.exists():
                    shutil.rmtree(mirror_dir)
                mirror_dir.mkdir()
                check_returncode(subprocess.run(
                    (spack, "mirror", "create", "--directory", mirror_dir, "--all"),
                    env=self._env_vars,
                    check=False,
                    capture_output=True,
                ))
                rel_mirror_dir = mirror_dir.resolve().relative_to(env_dir)
                check_returncode(subprocess.run(
                    (spack, "mirror", "add", name, rel_mirror_dir),
                    env=self._env_vars,
                    check=False,
                    capture_output=True,
                ), env=self._env_vars)

        # Ensure target specs are uninstalled
        with ch_tb.ctx(f"Uninstalling specs"):
            for spec in generalized_specs:
                has_spec = subprocess.run(
                    [
                        spack, "find", spec,
                    ],
                    env=self._env_vars,
                    check=False,
                    capture_output=True,
                ).returncode == 0
                if has_spec:
                    check_returncode(subprocess.run(
                        [
                            spack, "uninstall", "--all", "--yes", "--force", *spec,
                        ],
                        check=False,
                        capture_output=True,
                        env=self._env_vars,
                    ), env=self._env_vars)
        
    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        spack = workdir / "spack/bin/spack"
        assert self._env_dir
        assert "LD_PRELOAD" not in self._env_vars
        assert "LD_LIBRARY_PATH" not in self._env_vars
        assert "HOME" not in self._env_vars
        # env=patchelf%400.13.1%3A0.13%20%25gcc%20target%3Dx86_64-openblas
        # env - PATH=$PWD/result/bin HOME=$HOME $(jq  --join-output --raw-output 'to_entries[] | .key + "=" + .value + " "' .workdir/work/spack_envs/$env/env_vars.json) .workdir/work/spack/bin/spack --debug bootstrap status 2>~/Downloads/stderr_good.txt >~/Downloads/stdout_good.txt
        # sed -i $'s/\033\[[0-9;]*m//g' ~/Downloads/stderr*.txt
        # sed -i 's/==> \[[0-9:. -]*\] //g' ~/Downloads/stderr*.txt
        return (
            (spack, "--debug", "install"),
            {k: v for k, v in self._env_vars.items()},
        )


class KaggleNotebook(Workload):
    kind = "data science"

    def __init__(
            self,
            kernel: str,
            competition: str,
            replace: Sequence[tuple[str, str]],
    ) -> None:
        # kaggle kernels pull pmarcelino/comprehensive-data-exploration-with-python
        # kaggle competitions download -c house-prices-advanced-regression-techniques
        self._kernel = kernel
        self._competition = competition
        self._replace = replace
        self._notebook: None | Path = None
        self._data_zip: None | Path = None
        self.name = self._kernel.replace("/", "-")
 
    def setup(self, workdir: Path) -> None:
        self._notebook = workdir / "kernel" / (self._kernel.split("/")[1] + ".ipynb")
        self._data_zip = workdir / (self._competition.split("/")[1] + ".zip")
        if not self._notebook.exists():
            check_returncode(subprocess.run(
                [
                    result_bin / "kaggle", "kernels", "pull", "--path",
                    workdir / "kernel", self._kernel
                ],
                env={"PATH": str(result_bin)},
                check=False,
                capture_output=True,
            ))
            notebook_text = self._notebook.read_text()
            for bad, good in self._replace:
                notebook_text = notebook_text.replace(bad, good)
            self._notebook.write_text(notebook_text)
        if not self._data_zip.exists():
            check_returncode(subprocess.run(
                [
                    result_bin / "kaggle", "competitions", "download", "--path",
                    workdir, self._competition.split("/")[1]
                ],
                check=False,
                capture_output=True,
            ))
        if (workdir / "input").exists():
            shutil.rmtree(workdir / "input")
        check_returncode(subprocess.run(
            [result_bin / "unzip", "-o", "-d", workdir / "input", self._data_zip],
            env={"PATH": str(result_bin)},
            check=False,
            capture_output=True,
        ))

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        assert self._notebook
        return (
            (
                (result_bin / "python").resolve(), "-m", "jupyter", "nbconvert", "--execute",
                "--to=markdown", self._notebook,
            ),
            {"PATH": str(result_bin)},
        )


# if __name__ == "__main__":
#     SpackInstall(["patchelf@0.13.1:0.13 %gcc target=x86_64", "openblas"]).test(Path(".workdir/work"))


WORKLOADS: Sequence[Workload] = (
    # *tuple(
    #     SpackInstall([spec])
    #     for spec in xsdk_specs
    # ),
    # SpackInstall(["kokkos"]),
    # SpackInstall(["dakota"]),
    # SpackInstall(["uqtk"]),
    # SpackInstall(["qthreads"]),
    KaggleNotebook(
        "pmarcelino/comprehensive-data-exploration-with-python",
        "competitions/house-prices-advanced-regression-techniques",
        replace=(
            (".corr()", ".corr(numeric_only=True)"),
            (
                "df_train['SalePrice'][:,np.newaxis]",
                "df_train['SalePrice'].values[:,np.newaxis]",
            ),
            (
                "df_train.drop((missing_data[missing_data['Total'] > 1]).index,1)",
                "df_train.drop((missing_data[missing_data['Total'] > 1]).index, axis=1)",
            ),
        ),
    ),
    KaggleNotebook(
        "startupsci/titanic-data-science-solutions",
        "competitions/titanic",
        replace=(
            (
                "sns.FacetGrid(train_df, col='Survived', row='Pclass', size=",
                "sns.FacetGrid(train_df, col='Survived', row='Pclass', height=",
            ),
            (
                "sns.FacetGrid(train_df, row='Embarked', size=",
                "sns.FacetGrid(train_df, row='Embarked', height=",
            ),
            (
                "sns.FacetGrid(train_df, row='Embarked', col='Survived', size=",
                "sns.FacetGrid(train_df, row='Embarked', col='Survived', height=",
            ),
            (
                "sns.FacetGrid(train_df, row='Pclass', col='Sex', size=",
                "sns.FacetGrid(train_df, row='Pclass', col='Sex', height=",
            )
        ),
    ),
    KaggleNotebook(
        "ldfreeman3/a-data-science-framework-to-achieve-99-accuracy",
        "competitions/titanic",
        replace=(
            (
                "from sklearn.preprocessing import Imputer , Normalizer",
                (
                    "from sklearn.impute import SimpleImputer as Imputer; "
                    "from sklearn.preprocessing import Normalizer"
                ),
            ),
            (
                "from pandas.tools.plotting import scatter_matrix",
                "from pandas.plotting import scatter_matrix",
            ),
            ("sns.factorplot(", "sns.catplot("),
            (".corr()", ".corr(numeric_only=True)"),
            (
                "data2.set_value(index, 'Random_Predict', 0)",
                "data2.loc[index, 'Random_Predict'] = 0",
            ),
            (
                "data2.set_value(index, 'Random_Predict', 1)",
                "data2.loc[index, 'Random_Predict'] = 1",
            ),
        ),
    ),
    KaggleNotebook(
        "yassineghouzam/titanic-top-4-with-ensemble-modeling",
        "competitions/titanic",
        replace=(
            ("sns.factorplot(", "sns.catplot("),
            (
                'sns.catplot(x=\"SibSp\",y=\"Survived\",data=train,kind=\"bar\", size',
                'sns.catplot(x=\"SibSp\",y=\"Survived\",data=train,kind=\"bar\", height',
            ),
            (
                'sns.catplot(x=\"Parch\",y=\"Survived\",data=train,kind=\"bar\", size',
                'sns.catplot(x=\"Parch\",y=\"Survived\",data=train,kind=\"bar\", height',
            ),
            (
                'sns.catplot(x=\"Pclass\",y=\"Survived\",data=train,kind=\"bar\", size',
                'sns.catplot(x=\"Pclass\",y=\"Survived\",data=train,kind=\"bar\", height',
            ),
            (
                'sns.catplot(x=\"Pclass\", y=\"Survived\", hue=\"Sex\", data=train,\n                   size',
                'sns.catplot(x=\"Pclass\", y=\"Survived\", hue=\"Sex\", data=train,\n                   height'),
            (
                'sns.catplot(x=\"Embarked\", y=\"Survived\",  data=train,\n                   size',
                'sns.catplot(x=\"Embarked\", y=\"Survived\",  data=train,\n                   height',
            ),
            (
                'sns.catplot(x=\"Pclass\", col=\"Embarked\",  data=train,\n                   size',
                'sns.catplot(x=\"Pclass\", col=\"Embarked\",  data=train,\n                   height',
            ),
            (
                'g = g.set_xticklabels([\"Master\",\"Miss/Ms/Mme/Mlle/Mrs\",\"Mr\",\"Rare\"])',
                "",
            ),
            (
                'g = sns.countplot(dataset[\\"Cabin\\"],order=[\'A\',\'B\',\'C\',\'D\',\'E\',\'F\',\'G\',\'T\',\'X\'])',
                "",
            ),
            (
                'g = sns.barplot(\\"CrossValMeans\\",\\"Algorithm\\",data = cv_res, palette=\\"Set3\\",orient = \\"h\\",**{\'xerr\':cv_std})',
                "",
            ),
            ('g.set_xlabel(\"Mean Accuracy\")', ""),
            ('g = g.set_title(\\"Cross validation scores\\")', ""),
            ('\'loss\' : [\\"deviance\\"]', '\'loss\' : [\\"log_loss\\"]'),
        ),
    ),
    # SpackInstall(["patchelf@0.13.1:0.13 %gcc target=x86_64", "openblas"]),
    # SpackInstall(["hdf5"]),
    # SpackInstall(["mpich"]),
    # SpackInstall(["mvapich2"]),
    # SpackInstall(["py-matplotlib"]),
    # SpackInstall(["gromacs"]),
    # SpackInstall(["r"]),
)
