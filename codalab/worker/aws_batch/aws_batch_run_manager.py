import httplib
import logging
import os
import psutil
from subprocess import PIPE, Popen
import threading
import time
import socket

import boto3
import docker

from codalab.lib.formatting import parse_size
from codalab.worker.state_committer import JsonStateCommitter
from codalab.worker.run_manager import BaseRunManager
from codalab.worker.bundle_state import BundleInfo, RunResources, WorkerRun

from .aws_batch_run_state import AWSBatchRunStateMachine, AWSBatchRunStage, AWSBatchRunState

logger = logging.getLogger(__name__)


class AwsBatchRunManager(BaseRunManager):

    BUNDLE_DIR_WAIT_NUM_TRIES = 120

    def __init__(
        self,
        worker,  # type: Worker
        work_dir,  # type: str
        commit_file,  # type: str
        batch_queue,  # type: str
        queue_name,  # type: str
    ):
        self._worker = worker
        self._state_committer = JsonStateCommitter(commit_file)
        self._stop = False
        self._work_dir = work_dir
        self._batch_queue = batch_queue
        self._batch_client = boto3.client('batch')
        self._runs = {}  # type: Dict[str, AWSBatchRunState]
        self._lock = threading.RLock()
        self._run_state_manager = AWSBatchRunStateMachine(
            batch_client=self._batch_client, batch_queue=self._batch_queue
        )

    def start(self):
        """
        starts the RunManager, initializes from committed state, starts other
        dependent managers and initializes them as well.
        """
        self.load_state()

    def stop(self):
        """
        Starts any necessary cleanup and propagates to its other managers
        Blocks until cleanup is complete and it is safe to quit
        """
        self._stop = True

    def save_state(self):
        """
        makes the RunManager and all other managers commit their state to
        disk (including state of all runs)
        """
        self._state_committer.commit(self._runs)

    def load_state(self):
        self._runs = self._state_committer.load()

    def process_runs(self):
        """
        Main event-loop call where the run manager should advance the state
        machine of all its runs
        """
        with self._lock:
            for bundle_uuid in self._runs.keys():
                run_state = self._runs[bundle_uuid]
                self._runs[bundle_uuid] = self._run_state_manager.transition(run_state)
            self._runs = {
                k: v for k, v in self._runs.items() if v.stage != AWSBatchRunStage.FINISHED
            }

    def create_run(self, bundle, resources):
        """
        Creates and starts processing a new run with the given bundle and
        resources
        """
        if self._stop:
            # Run Manager stopped, refuse more runs
            return
        run_state = AWSBatchRunState(
            stage=AWSBatchRunStage.INITIALIZING,
            is_killed=False,
            is_finalized=False,
            is_finished=False,
            bundle=bundle,
            resources=resources,
            run_status="Initializing",
            bundle_dir_wait_num_tries=self.BUNDLE_DIR_WAIT_NUM_TRIES,
            batch_job_definition=None,
            batch_job_id=None,
            disk_utilization=0,
            failure_message=None,
            kill_message=None,
        )
        with self._lock:
            self._runs[bundle.uuid] = run_state

    def has_run(self, uuid):
        """
        Returns True if the run with the given UUID is managed
        by this RunManager, False otherwise
        """
        return uuid in self._runs

    def mark_finalized(self, uuid):
        """
        Marks the run with the given uuid as finalized server-side so the
        run manager can discard it completely
        """
        if uuid in self._runs:
            with self._lock:
                self._runs[uuid] = self._runs[uuid]._replace(finalized=True)

    def write(self, uuid, path, string):
        """
        Write string to path in bundle with uuid
        """
        run_state = self._runs[uuid]
        if os.path.normpath(path) in set(dep.child_path for dep in run_state.bundle.dependencies):
            return
        with open(os.path.join(run_state.bundle_path, path), 'w') as f:
            f.write(string)

    def netcat(self, uuid, port, message, reply):
        """
        Write message to port of bundle with uuid and read the response.
        Returns a stream with the response contents
        """
        err = (httplib.BAD_REQUEST, "Netcat not supported for AWS Batch workers")
        reply(err)

    def kill(self, uuid):
        """
        Kill bundle with uuid
        """
        run_state = self._runs[uuid]
        with self._lock:
            run_state = run_state._replace(kill_message='Kill requested', is_killed=True)
            self._runs[run_state.bundle.uuid] = run_state

    @property
    def all_runs(self):
        """
        Returns a list of all the runs managed by this RunManager
        """
        with self._lock:
            return [
                WorkerRun(
                    uuid=run_state.bundle.uuid,
                    run_status=run_state.run_status,
                    bundle_start_time=run_state.bundle_start_time,
                    container_time_total=run_state.container_time_total,
                    container_time_user=run_state.container_time_user,
                    container_time_system=run_state.container_time_system,
                    docker_image=run_state.docker_image,
                    state=AWSBatchRunStage.WORKER_STATE_TO_SERVER_STATE[run_state.stage],
                    remote=self._worker.id,
                    exitcode=run_state.exitcode,
                    failure_message=run_state.failure_message,
                )
                for run_state in self._runs.values()
            ]

    @property
    def all_dependencies(self):
        """
        Returns a list of all dependencies available in this RunManager
        """
        return []

    @property
    def cpus(self):
        """
        Total number of CPUs this RunManager has
        """
        # TODO: Read from batch
        return 10000

    @property
    def gpus(self):
        """
        Total number of GPUs this RunManager has
        """
        # TODO: Read from batch
        return 10000

    @property
    def memory_bytes(self):
        """
        Total installed memory of this RunManager
        """
        # TODO: Read from batch
        return parse_size('10000t')

    @property
    def free_disk_bytes(self):
        # TODO: Read from batch
        return parse_size('10000t')
