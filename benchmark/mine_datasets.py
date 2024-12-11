import subprocess


subprocess.run(["git", "clone", "https://github.com/spack/spack/", "spack"], check=True, capture_output=True)
