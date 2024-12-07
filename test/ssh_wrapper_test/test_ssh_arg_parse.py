import sys
from probe_py.manual.ssh_argparser import parse_ssh_args

# List of test cases
test_cases = [
    (['-v'], (['-v'], None, [])),
    (['-p', '22'], (['-p', '22'], None, [])),
    (['-v', '-A', '-q'], (['-v', '-A', '-q'], None, [])),
    (['-p', '22', 'user@host.com'], (['-p', '22'], 'user@host.com', [])),
    (['user@host.com', 'uptime'], ([], 'user@host.com', ['uptime'])),
    (['-p', '22', 'user@host.com', 'ls', '-la'], (['-p', '22'], 'user@host.com', ['ls', '-la'])),
    (['-A', 'user@host.com', 'echo', '"Hello World"'], (['-A'], 'user@host.com', ['echo', '"Hello World"'])),
    (['-o', 'StrictHostKeyChecking=no', 'user@host.com'], (['-o', 'StrictHostKeyChecking=no'], 'user@host.com', [])),
    (['-v', '-p', '22', '-A', 'user@host.com', 'uptime'], (['-v', '-p', '22', '-A'], 'user@host.com', ['uptime']))
]

def run_test_cases():
    for i, (input_args, expected_output) in enumerate(test_cases):
        result = parse_ssh_args(input_args)
        if result == expected_output:
            print(f"Test case {i+1} passed!")
        else:
            print(f"Test case {i+1} failed!")
            print(f"Input: {input_args}")
            print(f"Expected: {expected_output}")
            print(f"Got: {result}")


if __name__ == "__main__":
    run_test_cases()
