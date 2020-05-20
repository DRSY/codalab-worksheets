import argparse
import logging
import os
import uuid
import subprocess
import getpass
from pathlib import Path
import random

from codalab.worker.bundle_state import State
from .worker_manager import WorkerManager, WorkerJob

logger = logging.getLogger(__name__)


class SlurmBatchWorkerManager(WorkerManager):
    NAME = 'slurm-batch'
    DESCRIPTION = 'Worker manager for submitting jobs using Slurm Batch'

    SRUN_COMMAND = 'srun'
    SBATCH_COMMAND = 'sbatch'
    SBATCH_PREFIX = '#SBATCH'
    SQUEUE_COMMAND = 'squeue'

    @staticmethod
    def add_arguments_to_subparser(subparser):
        subparser.add_argument(
            '--job-definition-name',
            type=str,
            default='codalab-slurm-worker',
            help='Name for the job definitions that will be generated by this worker manager',
        )
        subparser.add_argument(
            '--nodelist', type=str, default='', help='The worker node to run jobs in'
        )
        subparser.add_argument(
            '--partition', type=str, default='jag-standard', help='Name of batch job queue to use'
        )
        subparser.add_argument(
            '--cpus', type=int, default=1, help='Default number of CPUs for each worker'
        )
        subparser.add_argument(
            '--gpus', type=int, default=1, help='Default number of GPUs for each worker'
        )
        subparser.add_argument(
            '--memory-mb', type=int, default=2048, help='Default memory (in MB) for each worker'
        )
        subparser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print out Slurm batch job definition without submitting to Slurm',
        )

    def __init__(self, args, codalab_client):
        super().__init__(args)
        self.username = getpass.getuser()

    def get_worker_jobs(self):
        """
        Return a list of jobs.
        """
        # Get all the Slurm workers that are owned by the current user.
        # Returning result will be in the following format:
        # JOBID:STATE
        # 1478828:PENDING
        # 1478830:PENDING
        jobs = self.run_command(['squeue', '-u', self.username, '-o', '%i:%T'])
        jobs = jobs.strip().split()[1:]
        logger.info('Workers: {}'.format(' '.join(job for job in jobs) or '(none)'))

        # Get all the RUNNING jobs that are owned by the current user.
        # Returning result will be in the following format:
        # JOBID
        # 1478828
        # 1478830
        running_jobs = self.run_command(
            ['squeue', '-u', self.username, '-t', 'RUNNING', '-o', '%i']
        )
        running_jobs = running_jobs.strip().split()[1:]

        return [WorkerJob(job) for job in running_jobs]

    def start_worker_job(self):
        """
        Start a CodaLab Slurm worker that submits batch job to Slurm
        """
        worker_id = uuid.uuid4().hex
        # user's local home directory for easy access
        work_dir = os.path.join(str(Path.home()), "slurm-batch-scratch/{}".format(worker_id))

        # This needs to be a unique directory since Batch jobs may share a host
        worker_network_prefix = 'cl_worker_{}_network'.format(worker_id)
        command = [
            'cl-worker',
            '--server',
            self.args.server,
            '--verbose',
            '--exit-when-idle',
            '--idle-seconds',
            str(self.args.worker_idle_seconds),
            '--work-dir',
            work_dir,
            '--id',
            worker_id,
            '--network-prefix',
            worker_network_prefix,
            # enforce tagging Slurm batch worker
            '--tag',
            self.args.worker_tag if self.args.worker_tag else self.args.job_definition_name,
            # always set in Slurm worker manager to ensure safe shutdown
            '--pass-down-termination',
        ]

        slurm_args = self.create_slurm_args(self.args)
        job_definition = self.create_job_definition(slurm_args=slurm_args, command=command)

        # Not submit job to Slurm if dry run
        if self.dry_run:
            return

        batch_script = os.path.join(work_dir, slurm_args['job-name'] + '.slurm')
        self.save_job_definition(batch_script, job_definition)
        self.run_command([self.SBATCH_COMMAND, batch_script])

    def run_command(self, command):
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, errors = proc.communicate()
        if output:
            logger.info(output)
            return output.decode()
        if errors:
            print(
                "Failed to executing {}: {}: {}".format(' '.join(command), errors, proc.returncode)
            )
            logger.error(errors)

    def save_job_definition(self, job_file, job_definition):
        """
        Save the batch job definition to file.
        :param job_file: a file storing the Slurm batch job configuration
        :param job_definition: the job definition of a Slurm batch job
        :return:
        """
        with open(job_file, 'w') as f:
            f.write('Slurm Batch Job Definition:\n')
            f.write(job_definition)
        logger.info("Saved the Slurm Batch Job Definition to {}".format(job_file))

    def create_job_definition(self, slurm_args, command):
        """
        Create a Slurm batch job definition structured as a list of Slurm batch arguments and a srun command
        :param slurm_args: arguments for launching a Slurm batch job
        :param command: arguments for starting a CodaLab worker
        :return: a string containing the Slurm batch job definition
        """
        sbatch_args = [
            '{} --{}={}'.format(self.SBATCH_PREFIX, key, slurm_args[key])
            for key in sorted(slurm_args.keys())
        ]
        # Using the --unbuffered option with srun command will allow output
        # appear in the output file as soon as it is produced.
        srun_args = [self.SRUN_COMMAND, '--unbuffered'] + command
        # job definition contains two sections: sbatch arguments and srun command
        job_definition = '#!/bin/bash\n\n' + '\n'.join(sbatch_args) + '\n' + ' '.join(srun_args)
        print(job_definition)
        return job_definition

    def create_random_job_name(self, job_definition_name):
        """
        Generate a random Slurm job name
        :param job_definition_name:
        :return: slurm job name
        """
        return self.username + "-" + job_definition_name + str(random.randint(0, 5000000))

    def create_slurm_args(self, args):
        """
        Convert command line arguments to Slurm
        :param args: command line arguments
        :return: a dictionary of Slurm arguments
        """
        slurm_args = {}
        slurm_args['nodelist'] = self.args.nodelist
        slurm_args['mem-per-cpu'] = self.args.memory_mb
        slurm_args['partition'] = self.args.partition
        slurm_args['gres'] = "gpu:" + str(self.args.gpus)
        # job-name is unique
        slurm_args['job-name'] = self.create_random_job_name(self.args.job_definition_name)
        slurm_args['cpus-per-task'] = 3
        slurm_args['ntasks-per-node'] = 1
        slurm_args['time'] = '10-0'
        slurm_args['open-mode'] = 'append'
        slurm_args['output'] = slurm_args['job-name'] + '.out'
        return slurm_args
