from test_cli import TestModule

import argparse
import random
import socket
import string
import subprocess
import sys
import time


class TestRunner(object):
    _CODALAB_SERVICE_SCRIPT = 'codalab_service.py'
    _TEMP_INSTANCE_NEEDED_TESTS = ['all', 'default', 'copy']

    @staticmethod
    def _docker_exec(command):
        return 'docker exec -it codalab_rest-server_1 /bin/bash -c "{}"'.format(command)

    @staticmethod
    def _create_temp_instance(name):
        def get_free_port():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', 0))
            port = str(s.getsockname()[1])
            s.close()
            return port

        rest_port = get_free_port()
        instance = 'http://rest-server:%s' % rest_port
        print('Creating another CodaLab instance {} at {} for testing...'.format(name, instance))

        try:
            start_time = time.time()
            subprocess.check_call(
                ' '.join(
                    [
                        'python3',
                        TestRunner._CODALAB_SERVICE_SCRIPT,
                        'start',
                        '--instance-name %s' % name,
                        '--rest-port %s' % rest_port,
                        '--version %s' % version,
                        '--services init rest-server',
                    ]
                ),
                shell=True,
            )
            print(
                'It took {} seconds to create the temp instance.'.format(time.time() - start_time)
            )
        except subprocess.CalledProcessError as ex:
            print('There was an error while creating the temp instance: %s' % ex.output)
            raise

        return instance

    def __init__(self, instance, tests):
        self.instance = instance
        self.tests = tests

        # Check if a second, temporary instance of CodaLab is needed for testing
        self.temp_instance_required = any(
            test in tests for test in TestRunner._TEMP_INSTANCE_NEEDED_TESTS
        )
        if self.temp_instance_required:
            self.temp_instance_name = 'temp-instance%s' % ''.join(
                random.choice(string.digits) for _ in range(8)
            )
            self.temp_instance = TestRunner._create_temp_instance(self.temp_instance_name)

    def run(self):
        success = True
        try:
            # Run backend tests using test_cli
            test_command = 'python3 test_cli.py --instance %s ' % self.instance
            if self.temp_instance_required:
                test_command += '--second-instance %s ' % self.temp_instance
            test_command += ' '.join(self.tests)

            print('Running backend tests with command: %s' % test_command)
            subprocess.check_call(TestRunner._docker_exec(test_command), shell=True)

            if 'frontend' in self.tests:
                self._run_frontend_tests()

        except subprocess.CalledProcessError as ex:
            print('Exception while executing tests: %s' % ex.output)
            success = False

        self._cleanup()
        return success

    def _run_frontend_tests(self):
        # Run Selenium UI tests
        subprocess.check_call('python3 tests/ui/ui_tester.py --headless', shell=True)

    def _cleanup(self):
        if not self.temp_instance_required:
            return

        print('Shutting down the temp instance {}...'.format(self.temp_instance_name))
        subprocess.check_call(
            ' '.join(
                [
                    'python3',
                    TestRunner._CODALAB_SERVICE_SCRIPT,
                    'stop',
                    '--instance-name %s' % self.temp_instance_name,
                ]
            ),
            shell=True,
        )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Runs the specified tests against the specified CodaLab instance (defaults to localhost)'
    )
    parser.add_argument(
        '--cl-executable',
        type=str,
        help='Path to CodaLab CLI executable, defaults to "cl"',
        default='cl',
    )
    parser.add_argument(
        '--version',
        type=str,
        help='CodaLab version to use for multi-instance tests, defaults to "latest"',
        default='latest',
    )
    parser.add_argument(
        '--instance',
        type=str,
        help='CodaLab instance to run tests against, defaults to "http://rest-server:2900"',
        default='http://rest-server:2900',
    )
    parser.add_argument(
        'tests',
        metavar='TEST',
        nargs='+',
        type=str,
        choices=list(TestModule.modules.keys()) + ['all', 'default', 'frontend'],
        help='Tests to run from: {%(choices)s}',
    )

    args = parser.parse_args()
    cl = args.cl_executable
    version = args.version
    test_runner = TestRunner(args.instance, args.tests)
    if not test_runner.run():
        sys.exit(1)
