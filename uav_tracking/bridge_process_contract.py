"""Pure command-line identity contract for separately owned Gazebo bridges.

This checks tokens read from /proc/PID/cmdline.  Process ownership, executable
and mapped-library hashes, and the actual configuration bytes are independent
checks performed by the caller.  No files or processes are accessed here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath, PureWindowsPath


_EXPECTED_KEYS = {"node_name", "config_file", "service_argument"}
_POSE_SERVICE_TYPE = "ros_gz_interfaces/srv/SetEntityPose"


def _nonempty_string(value):
    return isinstance(value, str) and bool(value) and "\0" not in value


def validate_split_bridge_argv(argv, expected, *, role):
    """Validate one actual clock/data bridge argv, or raise ``ValueError``.

    Only the registered node remap, ``config_file`` and ``use_sim_time``
    parameters are allowed.  A data bridge additionally takes exactly its
    registered SetEntityPose service before the ROS arguments.  Multiple
    ``--ros-args`` markers are allowed because launch can append another one;
    duplicate settings and parameter files are rejected, never overridden.

    Absolute POSIX and Windows configuration paths are accepted so the pure
    contract can also be exercised by native Windows fixtures.  The caller
    must bind the expected production path to its resolved installed file.
    """
    if not isinstance(role, str) or role not in {"clock", "data"}:
        raise ValueError("Bridge role must be clock or data")
    if not isinstance(expected, Mapping) or set(expected) != _EXPECTED_KEYS:
        raise ValueError("Expected bridge contract must have exactly three fields")
    node_name = expected["node_name"]
    config_file = expected["config_file"]
    service = expected["service_argument"]
    if not _nonempty_string(node_name) or any(char.isspace() for char in node_name):
        raise ValueError("Expected bridge node name must be nonempty")
    if not _nonempty_string(config_file) or not (
        PurePosixPath(config_file).is_absolute()
        or PureWindowsPath(config_file).is_absolute()
    ):
        raise ValueError("Expected bridge configuration must be an absolute path")
    if role == "clock":
        if service is not None:
            raise ValueError("Clock bridge cannot register a positional service")
    elif (
        not _nonempty_string(service)
        or service.count("@") != 1
        or not service.startswith("/")
        or service.split("@", 1)[0] == "/"
        or service.split("@", 1)[1] != _POSE_SERVICE_TYPE
        or any(char.isspace() for char in service)
    ):
        raise ValueError("Data bridge must register one absolute SetEntityPose service")

    if (
        not isinstance(argv, Sequence)
        or isinstance(argv, (str, bytes, bytearray))
        or not argv
        or any(not _nonempty_string(token) for token in argv)
    ):
        raise ValueError("Actual bridge argv must be a nonempty sequence of strings")
    command = list(argv)
    if PureWindowsPath(command[0]).name != "parameter_bridge":
        raise ValueError("Actual bridge executable basename must be parameter_bridge")

    seen = set()
    service_count = 0
    in_ros_arguments = False
    index = 1
    while index < len(command):
        token = command[index]
        if token == "--ros-args":
            in_ros_arguments = True
            index += 1
            continue
        if token in {"-r", "--remap", "-p", "--param"}:
            if not in_ros_arguments or index + 1 >= len(command):
                raise ValueError("Bridge ROS option is outside --ros-args or has no value")
            value = command[index + 1]
            if token in {"-r", "--remap"}:
                key = "node_name"
                if value != "__node:=" + node_name:
                    raise ValueError("Foreign or altered bridge node remap")
            elif value == "config_file:=" + config_file:
                key = "config_file"
            elif value == "use_sim_time:=true":
                key = "use_sim_time"
            else:
                raise ValueError("Foreign or altered bridge parameter")
            if key in seen:
                raise ValueError("Duplicate bridge setting: " + key)
            seen.add(key)
            index += 2
            continue
        if role == "data" and token == service and not in_ros_arguments:
            service_count += 1
            if service_count > 1:
                raise ValueError("Duplicate data bridge service")
            index += 1
            continue
        raise ValueError("Unexpected bridge argv token: " + token)

    if seen != {"node_name", "config_file", "use_sim_time"}:
        raise ValueError("Bridge argv lacks its unique node/configuration/sim-time settings")
    if service_count != int(role == "data"):
        raise ValueError("Bridge argv has the wrong positional service count")
    return {
        "bridge_role": role,
        "node_name": node_name,
        "config_file": config_file,
        "command": command,
    }
