import pathlib
from probe_py.remote_access import Host, HostPath
from probe_py.scp import parse_scp_args


def test_parse_scp_args() -> None:
    assert parse_scp_args(["test.txt", "host:", "user@host:", "host:test.txt", "user@host:test.txt", "test.txt"]) == (
        [
            HostPath(
                Host(network_name=None, username=None, ssh_options=[], scp_options=[]),
                path=pathlib.Path("test.txt"),
            ),
            HostPath(
                Host(network_name="host", username=None, ssh_options=[], scp_options=[]),
                path=pathlib.Path(),
            ),
            HostPath(
                Host(network_name="host", username="user", ssh_options=[], scp_options=[]),
                path=pathlib.Path(),
            ),
            HostPath(
                Host(network_name="host", username=None, ssh_options=[], scp_options=[]),
                path=pathlib.Path("test.txt"),
            ),
            HostPath(
                Host(network_name="host", username="user", ssh_options=[], scp_options=[]),
                path=pathlib.Path("test.txt"),
            ),
        ],
        HostPath(
            host=Host(network_name=None, username=None, ssh_options=[], scp_options=[]),
            path=pathlib.Path("test.txt")
        ),
    )
