import sys
import subprocess
import shutil
from pathlib import Path
import argparse 

def build_oci_image_from_directory(directory: Path, image_name: str, tag: str, tar_output: bool,
                                   docker_tar: bool, load_docker: bool, load_podman: bool) -> None:

    if not directory.is_dir():
        raise ValueError(f"The directory {directory} does not exist or is not a directory.")

    image_tag = f"{image_name}:{tag}"
    oci_tar_file = Path(f"{image_name}.tar")
    docker_tar_file = Path(f"{image_name}-docker.tar")

    try:
        container_id = subprocess.check_output(["buildah", "from", "scratch"]).strip().decode('utf-8')
        
        subprocess.run(
            ["buildah", "add", container_id, str(directory), "/"],
            check=True
        )

        subprocess.run(
            ["buildah", "commit", container_id, image_tag],
            check=True
        )
        print(f"OCI image '{image_tag}' built successfully from directory '{directory}'.")

        subprocess.run(
            ["buildah", "push", image_tag, f"oci-archive:{oci_tar_file}"],
            check=True
        )
        print(f"OCI image saved as '{oci_tar_file}'.")

        subprocess.run(
            ["buildah", "push", image_tag, f"docker-archive:{docker_tar_file}"],
            check=True
        )
        print(f"OCI image saved as Docker-compatible tar '{docker_tar_file}'.")

        if load_docker:
            subprocess.run(f"docker load -i {docker_tar_file}", shell=True, check=True)
            print(f"OCI image '{image_tag}' loaded into Docker.")

        if not load_podman:
            subprocess.run(f"podman rmi {image_tag} >/dev/null",shell=True)

        if load_podman:
            print(f"OCI image '{image_tag}' loaded into Podman.")

    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e}")
        raise

    finally:
        tar_dir = Path("tar")
        tar_dir.mkdir(exist_ok=True)

        if tar_output and oci_tar_file.exists():
            shutil.move(str(oci_tar_file), tar_dir / oci_tar_file.name)
            print(f"Moved OCI tar file to {tar_dir / oci_tar_file.name}")

        elif oci_tar_file.exists():
            oci_tar_file.unlink()
            print(f"Removed unused OCI tar file '{oci_tar_file}'.")

        if docker_tar and docker_tar_file.exists():
            shutil.move(str(docker_tar_file), tar_dir / docker_tar_file.name)
            print(f"Moved Docker tar file to {tar_dir / docker_tar_file.name}")

        elif docker_tar_file.exists():
            docker_tar_file.unlink()
            print(f"Removed unused Docker tar file '{docker_tar_file}'.")


def main():
    parser = argparse.ArgumentParser(description="Build an OCI image from a given directory.")

    parser.add_argument("directory", type=str, help="The directory containing the files to build the OCI image from.")
    parser.add_argument("image_name", type=str, help="The name of the OCI image.")
    parser.add_argument("image_tag", type=str, help="The tag of the OCI image.")

    parser.add_argument("--tar_output", action="store_true", help="Whether to output a tar file of the image.")
    parser.add_argument("--docker_tar", action="store_true", help="Whether to create a Docker-compatible tar file.")
    parser.add_argument("--load_docker", action="store_true", help="Whether to load the image into Docker.")
    parser.add_argument("--load_podman", action="store_true", help="Whether to load the image into Podman.")

    args = parser.parse_args()

    target_directory = Path(args.directory)

    try:
        build_oci_image_from_directory(target_directory, args.image_name, args.image_tag, 
                                       tar_output=args.tar_output, docker_tar=args.docker_tar, 
                                       load_docker=args.load_docker, load_podman=args.load_podman)

    except ValueError as ve:
        print(ve)
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":

    ## please remove the following lines when running the script using your own args
    sys.argv = [
    'container_image.py', 
    '--load_podman', 
    '--load_docker', 
    '--docker_tar', 
    '--tar_output', 
    '../../../../result', 
    'test', 
    'v1.0.0']
    main()

