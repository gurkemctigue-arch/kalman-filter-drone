"""Future isolated logger observation; no node, DDS, simulation or clock change.

NOT RUN when authored. This observes the current audit process only. It cannot
retroactively establish libraries or clocks used by historical detector jobs.
"""
from pathlib import Path
import hashlib
import json
import os
import sys
import time

MAX_FILE = 8 * 1024**2


def pin(path):
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if not path.is_file() or before.st_size > MAX_FILE:
        raise ValueError('Expected one bounded ordinary source/library: ' + str(path))
    data = path.read_bytes()
    after = path.stat()
    if len(data) != before.st_size or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('Source/library changed while hashing: ' + str(path))
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'device': after.st_dev, 'inode': after.st_ino}


def emit(value):
    print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def main():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Future root-scheduled Linux audit window only')
    names = ('RCUTILS_CONSOLE_OUTPUT_FORMAT', 'RCUTILS_COLORIZED_OUTPUT',
             'RCUTILS_LOGGING_USE_STDOUT', 'RCUTILS_LOGGING_BUFFERED_STREAM', 'LD_PRELOAD')
    prior_environment = {name: os.environ.get(name) for name in names}
    os.environ.update(RCUTILS_CONSOLE_OUTPUT_FORMAT=
                      '[{severity}] [{time}] [ns={time_as_nanoseconds}] [{name}]: {message}',
                      RCUTILS_COLORIZED_OUTPUT='0', RCUTILS_LOGGING_USE_STDOUT='0',
                      RCUTILS_LOGGING_BUFFERED_STREAM='0')
    # Deliberately delayed: authoring/AST checking does not import ROS.
    import rclpy.logging as logging
    import rclpy.impl.rcutils_logger as logger_source
    import rclpy.clock as clock_source
    import rclpy.time_source as time_source
    from rclpy.impl.implementation_singleton import rclpy_implementation
    from rclpy.clock_type import ClockType
    from rclpy.time import Time

    logging.initialize()  # rcutils logging only; no rclpy.init(), node or graph.
    try:
        logger = logging.get_logger('rcutils_prefix_clock_probe01')
        clock = clock_source.Clock(clock_type=ClockType.ROS_TIME)
        source = time_source.TimeSource()
        source.attach_clock(clock)
        source.ros_time_is_active = True
        inputs = [Path(__file__), Path(logging.__file__), Path(logger_source.__file__),
                  Path(clock_source.__file__), Path(time_source.__file__),
                  Path(rclpy_implementation.__file__)]
        map_data = Path('/proc/self/maps').read_bytes()
        if len(map_data) > 1024**2:
            raise ValueError('Unexpected oversized self maps')
        selected = {}
        for line in map_data.decode('utf-8').splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) != 6 or not fields[5].startswith('/'):
                continue
            path = fields[5]
            if not Path(path).name.startswith(('librcutils', 'librcl', '_rclpy')):
                continue
            if path.endswith(' (deleted)'):
                raise ValueError('Mapped logger dependency is deleted; preserve refusal')
            selected[path] = {'device': fields[3], 'inode': int(fields[4])}
        for path, identity in selected.items():
            actual = Path(path).stat()
            device = '{:02x}:{:02x}'.format(os.major(actual.st_dev), os.minor(actual.st_dev))
            if identity != {'device': device, 'inode': actual.st_ino}:
                raise ValueError('Mapped logger dependency differs from current pathname')
            inputs.append(Path(path))
        before = {str(path.resolve(strict=True)): pin(path) for path in inputs}
        emit({'kind': 'CURRENT_LOGGER_CLOCK_AUDIT_PROVENANCE_NOT_HISTORICAL_PROOF',
              'pid': os.getpid(), 'python_executable': str(Path(sys.executable).resolve(strict=True)),
              'prior_environment': prior_environment,
              'audit_environment': {name: os.environ.get(name) for name in names},
              'mapped_logger_libraries': selected, 'source_and_binary_pins': before,
              'node_or_dds_or_simulator_started': False})
        for event_id, sim_ns in enumerate((7_000_000_000, 9_000_000_000, 3_000_000_000, 3_000_000_000)):
            clock.set_ros_time_override(Time(nanoseconds=sim_ns, clock_type=ClockType.ROS_TIME))
            system_before, steady_before = time.time_ns(), time.monotonic_ns()
            logger.info('RCUTILS_PREFIX_CLOCK_PROBE ' + json.dumps(
                {'event_id': event_id, 'controlled_ros_clock_ns': clock.now().nanoseconds},
                sort_keys=True, allow_nan=False, separators=(',', ':')))
            steady_after, system_after = time.monotonic_ns(), time.time_ns()
            emit({'kind': 'LOG_CALL_BRACKET_ONLY_NOT_WORKER_ENDPOINT', 'event_id': event_id,
                  'system_before_ns': system_before, 'system_after_ns': system_after,
                  'steady_before_ns': steady_before, 'steady_after_ns': steady_after,
                  'controlled_ros_clock_ns': clock.now().nanoseconds})
            time.sleep(.02)
        after = {str(path.resolve(strict=True)): pin(path) for path in inputs}
        emit({'kind': 'CURRENT_LOGGER_CLOCK_AUDIT_SOURCE_RECHECK',
              'source_and_binary_pins_unchanged': before == after,
              'clock_source_conclusion_created': False,
              'historical_process_provenance_established': False})
    finally:
        logging.shutdown()


if __name__ == '__main__':
    main()
