#!/usr/bin/env python3
# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import collections
import concurrent
import concurrent.futures
import datetime
import io
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

try:
    import config
    BOARDS_MAPPING = config.BOARDS_MAPPING
except ImportError:
    BOARDS_MAPPING = {}

_MAX_EMERGES = 32
_MAX_EMERGES_WITHOUT_UNITTEST = 50

_MAX_BUILD_PACKAGES = 3


class State(threading.Thread):
    """Describes states for the running checker."""

    def __init__(self, update_internval):
        """Initializes State"""
        super(State, self).__init__()
        # A lock to modify states/msgs.
        self.in_use = threading.Lock()
        # A map from board name to state name.
        self.states = {}
        # A map from board name to detail messages.
        self.msgs = {}
        # Time when State is created.
        self.initialized_time = datetime.datetime.now().replace(microsecond=0)
        # Map from board name to list of failed boards.
        self.failed = {}
        # A event to stop the thread.
        self.stop_print_event = threading.Event()
        # Update interval.
        self.update_internval = update_internval

    def set_failed(self, board, packages):
        """
        Sets failed packages for a board.

        Args:
            board: board to set.
            packages: failed packages.
        """
        with self.in_use:
            self.failed[board] = packages

    def failed_matrix(self, delimiter=' ', align=True):
        """
        Returns a failed matrix in string.

        Failed matrix is a string containing multiple lines.

        The first line is header.
        From the 2nd line, each line contains information for a board. delimited
        by the delimiter parameter.

        For the information line, the first element is the board name. From the
        second element, it is either empty or an 'X' meaning the corresponding
        packages failed on this board.

        Args:
            delimiter: delimiter to separate.
            align: should add extra space to make it aligned.
        """
        packages = set()
        for failed in self.failed.values():
            packages.update(failed)
        max_packages_len = max(
            len(p) for p in packages) if align and packages else 0
        header = ' ' * max_packages_len + delimiter + delimiter.join(
            sorted(self.failed.keys())) + '\n'
        data = []
        for package in packages:
            line = []
            package_format = '%%%ds' % (max_packages_len)
            line.append(package_format % (package))
            for board, failed in sorted(self.failed.items()):
                line.append(delimiter)
                if align:
                    line.append(' ' * (len(board) - 1))
                if package in failed:
                    line.append('X')
                else:
                    line.append(' ')
            line.append('\n')
            data.append(''.join(line))
        return ''.join([header] + data)

    def update(self, board, board_state, board_msg=''):
        """
        Updates state.

        Args:
            board: board to update.
            board_state: new state of the board.
            board_msg: message to display for the board.
        """
        with self.in_use:
            self.states[board] = board_state
            self.msgs[board] = board_msg

    def run(self):
        """Runs the thread to print status"""
        while not self.stop_print_event.is_set():
            with self.in_use:
                self.print()
            time.sleep(self.update_internval)

    def stop(self):
        """Stops printing status to screen"""
        self.stop_print_event.set()

    def print(self):
        """Prints current state to a new shell screen"""
        now = datetime.datetime.now().replace(microsecond=0)
        print("\033c            PARALLEL PACKAGES CHECKER")
        print('                           duration: %s, load: %s' %
              (now - self.initialized_time, os.getloadavg()))
        print()
        max_board_len = max(
            len(board_name) for board_name in self.states.keys())
        max_state_len = max(len(state) for state in self.states.values())
        for board in self.states.keys():
            board_state = self.states[board]
            board_msg = self.msgs[board]
            board_format = "%%%ds " % (max_board_len + 5,)
            state_format = "%%%ds " % (max_state_len + 5,)
            print(board_format % (board,), state_format % (board_state,),
                  '     ', board_msg)
        print()
        print('                              ', now)
        print()


class CheckOneBoard:
    """Threads for one board checker"""

    def __init__(self, board, state, log_dir, run_unittest):
        """
        Initializes CheckOneBoard.

        Args:
            board: name of the board.
            state: global state object.
            log_dir: log_dir of the the board.
            run_unittest: whether to run unittest.
        """
        self.board = board
        self.state = state
        self.state.update(board, 'pending')
        self.log_dir = log_dir
        self.run_unittest = run_unittest

        self.dependency_graph = None
        self.packages_to_verify = None

        self.scheduled_emerge = set()
        self.completed_emerge = set()
        self.passing_emerge = set()
        self.failed_emerge = set()

    def setup_board(self):
        """Runs setup_board, and update state."""
        self.state.update(self.board, 'setup_board')
        proc = subprocess.Popen(['setup_board', '--board', self.board],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        for line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):
            line = line.strip()
            if line:
                self.state.update(self.board, 'setup_board', line)
        proc.wait()
        if proc.returncode != 0:
            self.state.update(self.board, 'failed',
                              'setup_board failed. further steps skipped.')
            return
        self.state.update(self.board, 'setup_board', 'setup_board completed.')

    def cros_workon_start(self, packages):
        """
        Runs cros_workon start for selected client packages.
        Ignore any failing messsage since the package might not be used on all
        the boards.
        """
        self.state.update(self.board, 'cros workon start', packages)
        for package in packages.split():
            self._cros_workon('start', package, fail_silent=True)

    def build_packages(self):
        """Runs build_packages"""
        # cros_workon stop libchrome
        if not self._cros_workon('stop', 'libchrome'):
            return

        # build_packages
        # build_packages fails somtimes under high system load, allow maximum 3
        # times of retry.
        build_succeeded = False
        for trial in range(3):
            if self._build_packages():
                build_succeeded = True
                break
        if not build_succeeded:
            self.state.update(self.board, 'failed',
                              'build_packages failed. further steps skipped.')
            return
        self.state.update(self.board, 'build_packages',
                          'build_packages completed.')

    def emerge_libchrome(self):
        """Emerges libchrome"""
        # cros_workon start libchrome
        if not self._cros_workon('start', 'libchrome'):
            return

        # Emerge new libchrome.
        if not self._emerge_blocking('libchrome'):
            return

    def set_emerge_scheduled(self, package):
        """
        Sets emerge state for one package to scheduled.

        Args:
            package: package name.
        """
        self.scheduled_emerge.add(package)
        self._update_emerge_state()

    def handle_emerge_result_fn(self, package):
        """
        Handles emerge result.

        Args:
            package: package name.
        """

        def _handle_emerge_result(future):
            ret = False
            try:
                ret = future.result()
            finally:
                # TODO: distinguish failure and exception.
                if ret:
                    self.set_emerge_pass(package)
                else:
                    self.set_emerge_failed(package)

        return _handle_emerge_result

    def set_emerge_pass(self, package):
        """
        Sets emerge state for one package to passing

        Args:
            package: package name.
        """
        self.completed_emerge.add(package)
        self.passing_emerge.add(package)
        self.scheduled_emerge.remove(package)
        self._update_emerge_state()

    def set_emerge_failed(self, package):
        """
        Sets emerge state for one package to failed.

        Args:
            package: package name.
        """
        self.completed_emerge.add(package)
        self.failed_emerge.add(package)
        self.scheduled_emerge.remove(package)
        self._update_emerge_state()

    def emerge(self, package):
        """
        Emerge a single package.

        Args:
            package: package name.
        """
        log_dir = os.path.join(self.log_dir, package)
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'emerge_log'), 'w') as f:
            build_success = self._emerge_blocking(package,
                                                  out=f,
                                                  update_state=False)
        if build_success:
            shutil.rmtree(log_dir)
            return True
        return False

    def build_dependency_graph(self):
        """Build and save the dependency graph for libchrome-related packages."""
        self.packages_to_verify = self._list_depended_by('libchrome')
        self.dependency_graph = self._build_dependency_graph(
            self.packages_to_verify)

    def buildable_packages(self):
        """
        Returns list of buildable packages

        Packages that are already scheduled, started, or completed, are excluded.
        """
        newly_buildable_packages = []
        pending_packages = []
        for package in self.packages_to_verify:
            if package in self.scheduled_emerge | self.completed_emerge:
                continue
            pending_packages.append(package)
            dependency_satisfied = True
            for dependency in self.dependency_graph[package]:
                if dependency not in self.packages_to_verify:
                    continue
                if dependency not in self.completed_emerge:
                    dependency_satisfied = False
                    break
            if dependency_satisfied:
                newly_buildable_packages.append(package)

        # Has buildable packages.
        if newly_buildable_packages:
            return newly_buildable_packages
        # Wait for packages not yet completed.
        if self.scheduled_emerge:
            return []
        # Return any pending_packages to restart build with cyclced dependency.
        if pending_packages:
            return pending_packages[0:1]
        # Build complete.
        return []

    def _update_emerge_state(self):
        """Updates state for emerge stage."""
        self.state.update(
            self.board,
            'FEATURES=test emerge' if self.run_unittest else 'emerge',
            'Queued/Running:%d, Completed:%d (Passing:%d, Failed:%d), Total:%d'
            % (len(self.scheduled_emerge), len(self.completed_emerge),
               len(self.passing_emerge), len(
                   self.failed_emerge), len(self.packages_to_verify)))

    def _cros_workon(self, action, package, fail_silent=False):
        """
        Runs cros_workon-$BOARD, and update state.

        Returns True on sucess, False otherwise.
        """
        assert action in ['start', 'stop']
        self.state.update(self.board, 'cros workon ' + action,
                          'cros workon ' + action + ' ' + package)
        proc = subprocess.run(['cros', 'workon', '--board=' + self.board,
                               action, package],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        if proc.returncode != 0 and not fail_silent:
            self.state.update(
                self.board, 'failed',
                'cros workon --board=$BOARD %s %s failed. ' %
                (action, package) + 'further steps skipped.')
            return False
        return True

    def _build_packages(
            self,
            params=[],
    ):
        """
        Runs build_packages, and update state.

        Return True on sucess, False otherwise.

        Args:
            params: extra params for build_packages command.
        """
        self.state.update(self.board, 'build_packages')

        proc = subprocess.Popen([
            'cros',
            'build-packages',
            '--board',
            self.board,
            '--withdev',
            '--skip-setup-board',
        ] + params,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        log = []
        for line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):
            log.append(line)
            line = line.strip()
            if line:
                self.state.update(self.board, 'build_packages', line)
        proc.wait()

        if proc.returncode != 0:
            # Only write log at build_packages failure
            with open(os.path.join(self.log_dir, 'build_packages'), 'w') as f:
                f.writelines(log)
            self.state.update(self.board, 'failed',
                              'build_packages failed. further steps skipped.')
            return False
        # Ensure build_packages deleted on success without error handling.
        shutil.rmtree(os.path.join(self.log_dir, 'build_packages'),
                      ignore_errors=True)
        return True

    def _emerge_blocking(self,
                         package,
                         out=subprocess.DEVNULL,
                         update_state=True):
        """
        Emerges a package, and update state.
        Run unittests (prepending FEATURES=test) if user requested. Note
        packages without test will be emerged normally.

        Returns True on sucess, False otherwise.

        Args:
            package: package to emerge.
        """
        if update_state:
            self.state.update(self.board, 'emerge_' + package)
        env = dict(os.environ)
        if self.run_unittest:
            env['FEATURES'] = 'test'
        proc = subprocess.run(
            ['emerge-' + self.board, package],
            stdout=out,
            stderr=out,
            env=env,
        )
        if proc.returncode != 0:
            if update_state:
                self.state.update(
                    self.board, 'failed',
                    ('FEATURES=test ' if self.run_unittest else '') +
                    'emerge-$BOARD ' + package +
                    ' failed. further steps skipped.')
            return False
        if update_state:
            self.state.update(self.board, 'emerge_' + package,
                              ('FEATURES=test ' if self.run_unittest else '') +
                              'emerge-$BOARD ' + package + ' completed.')
        return True

    def _build_dependency_graph(self, packages):
        """
        Builds dependency graph between packages

        Returns a dict from packages to list of dependencies.

        Args:
            packages: packages to build dependency graph.
        """
        depended_by = dict((p, self._list_depended_by(p)) for p in packages)
        dependency_graph = collections.defaultdict(list)
        for p, depend_on_p_packages in depended_by.items():
            for depend_on_p in depend_on_p_packages:
                if depend_on_p in packages:
                    dependency_graph[depend_on_p].append(p)
        return dependency_graph

    def _list_depended_by(self, package):
        """
        Lists packages depended by <package>.

        Returns a list of packages.

        Args:
            package: package to check.
        """
        self.state.update(self.board, 'enumerate_dependencies',
                          'Enumerating packages depending on ' + package)
        depended_by = []
        version_remove_re = re.compile('(.*?)(-[0-9.]+)?(-r[0-9]+)?$')
        proc = subprocess.Popen(['equery-' + self.board, 'd', package],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        outs, _ = proc.communicate()
        outs = outs.decode('utf-8').split('\n')
        # Line format
        # $group/$pkg-$ver-r$r (>=chromeos-base/libchrome-0.0.1-r$r:0/9999[cros-debug])
        # Example:
        # media-libs/cros-camera-v4l2_test-0.0.1-r399 (>=chromeos-base/libchrome-0.0.1-r117:0/9999[cros-debug])
        for line in outs:
            if not line:
                continue
            if line[0] == ' ':
                continue
            depended_by.append(
                version_remove_re.match(line.split(' ')[0]).group(1))
        return depended_by


def handle_exception(board, state, stage):
    """
    Handles exception caused in future.

    Returns a function to use as add_done_callback.

    Args:
        board: board name.
        state: the global variable that stores per-board states.
        stage: a stage name.
    """

    def _handle(future):
        try:
            future.result()
        except Exception as e:
            state.update(
                board, 'bug',
                "A bug occurred. Semephores may have not been released.\n" +
                traceback.format_exc())

    return _handle


def already_failed(state, work):
    """
    Checks if work is already failed.

    Args:
        state: the global variable that stores per board states.
        work: a CheckOneBoard instance.
    """
    return state.states[work.board] in ['bug', 'failed']


def main():
    assert os.getcwd(
    ) == '/mnt/host/source/src/scripts', 'Please run under Chrome OS chroot ~/trunk/src/scripts'
    parser = argparse.ArgumentParser(description='Build packages checker')
    parser.add_argument('-b',
                        '--boards',
                        metavar='boards',
                        action='append',
                        type=str,
                        help='Boards to check',
                        required=True)
    parser.add_argument('-d',
                        '--output-directory',
                        metavar='output_directory',
                        type=str,
                        help='Output directory of failed logs',
                        required=True)
    parser.add_argument('--allow-output-directory-exists',
                        metavar='allow_output_directory_exists',
                        action='store_const',
                        help="Dont't error if output directory exists",
                        const=True,
                        default=False)
    parser.add_argument('--unittest',
                        metavar='unittest',
                        action='store_const',
                        help='Run unittest',
                        const=True,
                        default=False)
    parser.add_argument('--skip-setup-board',
                        metavar='skip_setup_board',
                        help='Skip setup_board phase',
                        action='store_const',
                        const=True,
                        default=False)
    parser.add_argument('--skip-first-pass-build-packages',
                        metavar='skip_first_pass_build_packages',
                        help='Skip build_packages with stable libchrome',
                        action='store_const',
                        const=True,
                        default=False)
    parser.add_argument('--force-clean-buildroot',
                        metavar='force_clean_buildroot',
                        help='Force clean /build/$BOARD directory',
                        action='store_const',
                        const=True,
                        default=False)
    parser.add_argument('--max-build-packages',
                        metavar='max_build_packages',
                        help='Maximum parallization for build_packages',
                        type=int)
    parser.add_argument(
        '--max-emerges',
        metavar='max_emerges',
        help=
        'Maximum parallization for emerge(s). Default to %d (or %d when --unittest)'
        % (_MAX_EMERGES_WITHOUT_UNITTEST, _MAX_EMERGES),
        type=int)
    parser.add_argument(
        '-p',
        '--cros-workon-packages',
        metavar='cros_workon_packages',
        help=
        'Packages to use 9999 ebuild. A string of list of packages space-separated. Default to None (libchrome only).',
        type=str,
        default='')
    parser.add_argument(
        '--status-update-interval',
        metavar='status_update_interval',
        help='Interval for updating current status. every (f) seconds',
        type=int,
        default=1)

    arg = parser.parse_args(sys.argv[1:])

    max_build_packages = _MAX_BUILD_PACKAGES
    if arg.max_build_packages:
        max_build_packages = arg.max_build_packages

    max_emerges = _MAX_EMERGES if arg.unittest else _MAX_EMERGES_WITHOUT_UNITTEST
    if arg.max_emerges:
        max_emerges = arg.max_emerges

    if arg.skip_first_pass_build_packages:
        assert arg.skip_setup_board, '--skip-setup-board must be set for --skip-first-pass-build-packages'
    if arg.force_clean_buildroot:
        assert not arg.skip_setup_board, '--skip-setup-board cannot be set for --force-clean-buildroot'
        assert not arg.skip_first_pass_build_packages, '--skip-first-pass-build-packages cannot be set for --force-clean-buildroot'

    boards = []
    for board in arg.boards:
        if board in BOARDS_MAPPING:
            boards += BOARDS_MAPPING[board]
        else:
            boards.append(board)

    state = State(arg.status_update_interval)

    os.makedirs(arg.output_directory,
                exist_ok=arg.allow_output_directory_exists)

    if arg.force_clean_buildroot:
        subprocess.check_output(
            ['sudo', 'rm', '-rf'] +
            [os.path.join('/build', board) for board in boards])

    work_list = []
    for board in boards:
        log_dir = os.path.join(arg.output_directory, 'by-board', board)
        os.makedirs(log_dir, exist_ok=arg.allow_output_directory_exists)
        work = CheckOneBoard(board, state, log_dir, arg.unittest)
        work_list.append(work)

    state.start()

    if not arg.skip_setup_board:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            for work in work_list:
                if already_failed(state, work):
                    continue
                task = executor.submit(work.setup_board)
                task.add_done_callback(
                    handle_exception(work.board, state, 'setup_board'))

    if arg.cros_workon_packages:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_build_packages) as executor:
            for work in work_list:
                task = executor.submit(work.cros_workon_start,
                                       arg.cros_workon_packages)

    if not arg.skip_first_pass_build_packages:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_build_packages) as executor:
            for work in work_list:
                if already_failed(state, work):
                    continue
                state.update(work.board, 'waiting',
                             'waiting for build_packages to start.')
                task = executor.submit(work.build_packages)
                task.add_done_callback(
                    handle_exception(work.board, state, 'build_packages'))

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_emerges) as executor:
        for work in work_list:
            if already_failed(state, work):
                continue
            state.update(work.board, 'waiting',
                         'waiting for emerge_libchrome to start.')
            task = executor.submit(work.emerge_libchrome)
            task.add_done_callback(
                handle_exception(work.board, state, 'emerge_libchrome'))

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_emerges) as executor:
        for work in work_list:
            if already_failed(state, work):
                continue
            task = executor.submit(work.build_dependency_graph)
            task.add_done_callback(
                handle_exception(work.board, state, 'enumerate_dependencies'))

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_emerges) as executor:
        unfinished_emerges = set()
        while True:
            if unfinished_emerges:
                done, not_done = concurrent.futures.wait(
                    unfinished_emerges,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                unfinished_emerges = not_done

            for work in work_list:
                if already_failed(state, work):
                    continue
                for package in work.buildable_packages():
                    work.set_emerge_scheduled(package)
                    task = executor.submit(work.emerge, package)
                    task.add_done_callback(
                        work.handle_emerge_result_fn(package))
                    unfinished_emerges.add(task)

            if not unfinished_emerges:
                break

    for work in work_list:
        if already_failed(state, work):
            state.set_failed(work.board, set(['SYSTEM']))
        else:
            state.set_failed(work.board, work.failed_emerge)

    state.stop()
    state.join()
    state.print()

    if state.failed:
        for board, packages in state.failed.items():
            for package in packages:
                # SYSTEM is a placeholder pacakge indicating something wrong
                # with this checker when running task for some board.
                # SYSTEM placeholder package doesn't have any fail log to copy.
                # Skipping.
                if package == 'SYSTEM':
                    continue
                os.makedirs(os.path.join(arg.output_directory, 'by-packages',
                                         package),
                            exist_ok=True)
                shutil.copy(
                    os.path.join(arg.output_directory, 'by-board', board,
                                 package, 'emerge_log'),
                    os.path.join(arg.output_directory, 'by-packages', package,
                                 board))
        print(state.failed_matrix(delimiter='     '))
        with open(os.path.join(arg.output_directory, 'matrix.txt'), 'w') as f:
            f.write(state.failed_matrix(delimiter='     '))
        with open(os.path.join(arg.output_directory, 'matrix.csv'), 'w') as f:
            f.write(state.failed_matrix(delimiter=','))

    print("Completed. See logs at ", arg.output_directory)


if __name__ == '__main__':
    main()
