import typing
import subprocess

from utils import log


def run_command(command: str, print_output=False) -> (int, typing.List[str], typing.List[str]):
    process = subprocess.Popen(
        command,
        universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="backslashreplace"
    )

    stdout = []
    while True:
        process_stdout = process.stdout.readline()
        if process_stdout == "" and process.poll() is not None:
            break

        stdout.append(process_stdout.strip())
        if print_output and process_stdout:
            log.debug(process_stdout.strip())

    return_code = process.poll()
    stderr = process.stderr.readlines()

    return return_code, [x.strip() for x in stdout if x], [x.strip() for x in stderr if x]
