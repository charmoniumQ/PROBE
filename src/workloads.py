import charmonium.time_block as ch_tb
import shutil
import hashlib
import os
import pathlib
import subprocess
import re
import urllib.parse
import json
from collections.abc import Sequence, Mapping
from pathlib import Path
from typing import cast
from util import env_command, run_all, CmdArg


result_bin = Path(__file__).resolve().parent / "result/bin"


class Workload:
    kind: str
    name: str

    def setup(self, workdir: Path) -> None:
        pass

    def run(self, workdir: Path) -> Sequence[CmdArg]:
        return ["true"]

    def __str__(self) -> str:
        return self.name


class SpackInstall(Workload):
    kind = "compilation"

    def __init__(self, specs: list[str], version: str = "v0.20.1") -> None:
        self.name = "compile " + "+".join(specs)
        self._version = version
        self._env_dir: Path | None = None
        self._specs = specs

    @staticmethod
    def _get_env_vars(spack: Path, env_dir: Path, refresh: bool = False) -> Mapping[str, str]:
        if refresh or not (env_dir / "env_vars.json").exists():
            exports = subprocess.run(
                [spack, "env", "activate", "--sh", "--dir", env_dir],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
            pattern = re.compile("^export ([a-zA-Z0-9_]+)=(.*?);?$", flags=re.MULTILINE)
            env_vars = dict(
                (match.group(1), match.group(2))
                for match in pattern.finditer(exports)
            )
            (env_dir / "env_vars.json").write_text(json.dumps(env_vars))
        else:
            env_vars = json.loads((env_dir / "env_vars.json").read_text())
        return env_vars


    @staticmethod
    def _anonymous_env(
            spack: Path,
            specs: list[str],
            dest: Path,
            concretize: bool = True,
            install: bool = True,
    ) -> tuple[Path, Mapping[str, str]]:
        env_name = urllib.parse.quote("-".join(specs), safe="")
        if len(env_name) > 64:
            env_name = hashlib.sha256(env_name.encode()).hexdigest()[:64]
        env_dir = dest / env_name
        if not env_dir.exists():
            env_dir.mkdir(parents=True)
            subprocess.run(
                [spack, "env", "create", "--dir", env_dir],
                check=True,
                capture_output=True,
            )
        env_vars = SpackInstall._get_env_vars(spack, env_dir)
        proc = subprocess.run(
            [spack, "add", *specs],
            env={**os.environ, **env_vars},
            check=True,
            capture_output=True,
        )
        env_vars = SpackInstall._get_env_vars(spack, env_dir, refresh=True)
        spec_shorthand = ", ".join(spec.partition("@")[0] for spec in specs)
        if concretize and not (env_dir / "spack.lock").exists():
            with ch_tb.ctx(f"concretize {spec_shorthand}"):
                subprocess.run(
                    [spack, "concretize"],
                    env={**os.environ, **env_vars},
                    check=True,
                    capture_output=True,
                )
                env_vars = SpackInstall._get_env_vars(spack, env_dir, refresh=True)
        if install:
            with \
                 (env_dir / "spack_install_stdout").open("wb") as stdout, \
                 ch_tb.ctx(f"install {spec_shorthand}"):
                print(f"`tail --follow {env_dir}/spack_install_stdout` to check progress")
                proc = subprocess.run(
                    [spack, "install"],
                    env={**os.environ, **dict(env_vars.items())},
                    check=True,
                    stdout=stdout,
                    stderr=subprocess.PIPE,
                )
                env_vars = SpackInstall._get_env_vars(spack, env_dir, refresh=True)
        return env_dir, env_vars

    @staticmethod
    def _install_spack(spack_dir: Path, version: str) -> None:
        if not spack_dir.exists():
            subprocess.run(
                run_all(
                    (
                        result_bin / "git", "clone", "-c", "feature.manyFiles=true",
                        "https://github.com/spack/spack.git", spack_dir,
                    ),
                    (
                        result_bin / "git", "-C", spack_dir, "checkout",
                        version, "--force",
                    ),
                ),
                check=True,
                capture_output=True,
            )

    @staticmethod
    def _create_mirror(spack: Path, env_vars: Mapping[str, str], mirror_dir: Path, specs: list[str]) -> None:
        name = hashlib.sha256("-".join(specs).encode()).hexdigest()[:16]
        mirrors = subprocess.run(
            (spack, "mirror", "list"),
            env={**os.environ, **env_vars},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if name not in mirrors:
            mirror_dir.mkdir(exist_ok=True, parents=True)
            subprocess.run(
                (spack, "mirror", "create", "--directory", mirror_dir, *specs),
                env={**os.environ, **env_vars},
                check=True,
                capture_output=True,
            )
            subprocess.run(
                (spack, "mirror", "add", name, mirror_dir),
                env={**os.environ, **env_vars},
                check=True,
                capture_output=True,
            )

    @staticmethod
    def _get_deps(spack: Path, env_dir: Path) -> list[str]:
        script = "; ".join([
            "import spack.environment",
            f"env = spack.environment.Environment('{env_dir}')",
            "print('\\n'.join(map(str, set(env.all_specs()))))",
        ])
        env_vars = SpackInstall._get_env_vars(spack, env_dir)
        return list(filter(bool, subprocess.run(
            (spack, "python", "-c", script),
            env={**os.environ, **env_vars},
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().split("\n")))

    @staticmethod
    def _has_installed_spec(spack: Path, spec: str) -> bool:
        return subprocess.run(
            [
                spack, "find", spec,
            ],
            check=False,
            capture_output=True,
        ).returncode == 0

    @staticmethod
    def _uninstall_spec(spack: Path, spec: str) -> None:
        subprocess.run(
            [
                spack, "uninstall", "--all", "--yes", "--force", spec,
            ],
            check=True,
            capture_output=True,
        )


    def setup(self, workdir: Path) -> None:
        # Install spack
        spack_dir = workdir / "spack"
        SpackInstall._install_spack(spack_dir, self._version)
        spack = spack_dir / "bin" / "spack"

        # Concretize env with desired specs
        self._env_dir, _env_vars = SpackInstall._anonymous_env(
            spack, self._specs, workdir / "env", concretize=True,
            install=False,
        )

        # Find deps of that env
        required_specs = SpackInstall._get_deps(spack, self._env_dir)

        # Take out specs we asked for
        generalized_specs = [
            spec.partition("@")[0]
            for spec in self._specs
        ]
        direct_dependency_specs = [
            spec
            for spec in required_specs
            if spec.partition("@")[0] in generalized_specs
        ]
        indirect_dependency_specs = [
            spec
            for spec in required_specs
            if spec.partition("@")[0] not in generalized_specs
        ]

        # Install just dependency specs (if any)
        if required_specs:
            SpackInstall._anonymous_env(
                spack, indirect_dependency_specs, workdir / "env",
                concretize=True, install=True,
            )

        # Create mirror with source code of self._specs
        mirror = self._env_dir / "mirror"
        SpackInstall._create_mirror(spack, _env_vars, mirror, direct_dependency_specs)

        # Ensure target specs are uninstalled
        for spec in generalized_specs:
            if SpackInstall._has_installed_spec(spack, spec):
                SpackInstall._uninstall_spec(spack, spec)

        # Update vars
        SpackInstall._get_env_vars(spack, self._env_dir, refresh=True)
        
    def run(self, workdir: Path) -> Sequence[CmdArg]:
        spack = workdir / "spack/bin/spack"
        assert self._env_dir
        env_vars = SpackInstall._get_env_vars(spack, self._env_dir)
        assert "LD_PRELOAD" not in env_vars
        return env_command(
            env_vars=dict(env_vars.items()),
            cmd=(spack, "install"),
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
        self.name = self._kernel.partition("/")[1]
 
    def setup(self, workdir: Path) -> None:
        self._notebook = workdir / "kernel" / (self._kernel.split("/")[1] + ".ipynb")
        self._data_zip = workdir / (self._competition.split("/")[1] + ".zip")
        if not self._notebook.exists():
            subprocess.run(
                [
                    result_bin / "kaggle", "kernels", "pull", "--path",
                    workdir / "kernel", self._kernel
                ],
                check=True,
                capture_output=True,
            )
            notebook_text = self._notebook.read_text()
            for bad, good in self._replace:
                notebook_text = notebook_text.replace(bad, good)
            self._notebook.write_text(notebook_text)
        if not self._data_zip.exists():
            subprocess.run(
                [
                    result_bin / "kaggle", "competitions", "download", "--path",
                    workdir, self._competition.split("/")[1]
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [result_bin / "unzip", "-o", "-d", workdir / "input", self._data_zip],
                check=True,
                capture_output=True,
            )

    def run(self, workdir: Path) -> Sequence[CmdArg]:
        assert self._notebook
        return (
            result_bin / "python", "-m", "jupyter", "nbconvert", "--execute",
            "--to=markdown", self._notebook,
        )


WORKLOADS: Sequence[Workload] = (
    # *tuple(
    #     SpackInstall([spec])
    #     for spec in xsdk_specs
    # ),
    # SpackInstall(["kokkos"]),
    # SpackInstall(["dakota"]),
    # SpackInstall(["uqtk"]),
    # SpackInstall(["qthreads"]),
    SpackInstall(["openblas"]),
    SpackInstall(["hdf5"]),
    SpackInstall(["mpich"]),
    SpackInstall(["mvapich2"]),
    SpackInstall(["py-matplotlib"]),
    SpackInstall(["gromacs"]),
    SpackInstall(["r"]),
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
)
