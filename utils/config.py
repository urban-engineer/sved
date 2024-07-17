import json
import os
import pathlib


CONFIG = dict()


def _get_config_directory() -> pathlib.Path:
    """
    Get the path to the config directory based off its location to this file.  Up two directories, then into config

    :return: Path pointing to the config directory
    """
    return pathlib.Path(__file__).absolute().parent.parent.joinpath("config")


def _load_config_file() -> dict:
    return json.loads(_get_config_directory().joinpath("config.json").read_text())


def load_logging_config() -> dict:
    return json.loads(_get_config_directory().joinpath("logging.json").read_text())


def load_flags() -> dict:
    """
    Load various flags from environment and/or config file (in that order).

    Environment flags are UPPERCASE of the config file key, e.g. "auto-delete" in environment is "AUTO-DELETE"

    Flags supported:

    * auto-delete: delete input files after being successfully encoded

    :return: Dictionary of flags to change behavior, see above for list of flags
    """

    global CONFIG

    if CONFIG:
        return CONFIG
    else:
        flags = _load_config_file().get("flags", {})

        for key in flags.keys():
            flags[key] = flags.get(key, os.environ.get(key.upper(), None))

        for key, value in flags.items():
            if value is None:
                error_message = "Missing key [{}] in config file (flags->{})"
                error_message += " or environment ({})"
                raise ValueError(error_message.format(key, key, key.upper()))

        CONFIG = flags
        return flags


def load_rabbitmq_config() -> dict:
    # Load base config from file - this may or may not exist.
    broker_config = _load_config_file()["rabbitmq"]

    # Loading from environment
    broker_config["broker"] = os.environ.get("RABBITMQ_BROKER", broker_config.get("broker", None))
    broker_config["broker_port"] = os.environ.get("RABBITMQ_BROKER_PORT", broker_config.get("broker_port", None))
    broker_config["queue"] = os.environ.get("RABBITMQ_QUEUE", broker_config.get("queue", None))

    error_message = ""
    if not broker_config.get("broker", None):
        error_message = "Missing address/host of RabbitMQ Broker in environment (RABBITMQ_BROKER)"
        error_message += " or config file (rabbitmq->broker)"

    if not broker_config.get("broker_port", None):
        error_message = "Missing port of RabbitMQ Broker in environment (RABBITMQ_BROKER_PORT)"
        error_message += " or config file (rabbitmq->broker_port)"

    if not broker_config.get("queue", None):
        error_message = "Missing RabbitMQ queue name in environment (RABBITMQ_QUEUE)"
        error_message += " or config file (rabbitmq->queue)"

    if error_message:
        raise ValueError(error_message)

    return broker_config


def load_input_directory(create_directory=True) -> pathlib.Path:
    """
    Load the input directory from the environment or config file (in that order).

    :param create_directory: if set, will create the input folder if it doesn't exist (mostly for debug).
    :return: Path to input directory
    """

    # Load from environment, or config file if not defined in environment
    input_path = os.environ.get("INPUT_PATH", _load_config_file().get("paths", {}).get("input", None))

    # Error checking
    if not input_path:
        error_message = "Missing input path definition in environment (INPUT_PATH)"
        error_message += " or config file (paths->input)"
        raise ValueError(error_message)

    input_path = pathlib.Path(input_path).resolve()

    if create_directory:
        input_path.mkdir(exist_ok=True, parents=True)
    return input_path


def load_output_directory(create_directory=True) -> pathlib.Path:
    """
    Load the output directory from the environment or config file (in that order).

    :param create_directory: if set, will create the output folder if it doesn't exist (mostly for debug).
    :return: Path to output directory
    """

    # Load from environment, or config file if not defined in environment
    output_path = os.environ.get("OUTPUT_PATH", _load_config_file().get("paths", {}).get("output", None))

    # Error checking
    if not output_path:
        error_message = "Missing output path definition in environment (OUTPUT_PATH)"
        error_message += " or config file (paths->output)"
        raise ValueError(error_message)

    output_path = pathlib.Path(output_path).resolve()

    if create_directory:
        output_path.mkdir(exist_ok=True, parents=True)
    return output_path
