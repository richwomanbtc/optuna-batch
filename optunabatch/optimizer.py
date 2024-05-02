import asyncio
import json
import os
import pickle
from typing import Dict, Sequence
from uuid import uuid4

import optuna
import optuna.trial
from custom import create_study  # type: ignore
from google.cloud import batch_v1, storage  # type: ignore
from job import TrialWithValues  # type: ignore

ObjectiveValueType = float | Sequence[float] | None


def backup_trials(study: optuna.study.Study, bucket_name: str):
    storage_client = storage.Client()
    blob_name = f"{study.study_name}/trials.pkl"
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pickle.dumps(study.trials))


def upload_pickled_trial(trial: optuna.Trial, bucket_name: str, blob_name: str):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pickle.dumps(trial))


def download_pickled_trial_with_values(
    bucket_name: str, blob_name: str
) -> TrialWithValues:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return pickle.loads(blob.download_as_string())


async def wait_for_job(
    job: batch_v1.Job, bucket_name: str, result_blob_name: str
) -> TrialWithValues | None:
    client = batch_v1.BatchServiceClient()
    job_name = job.name

    # Poll the job until it is complete
    while True:
        job = client.get_job(name=job_name)
        match job.status.state:
            case batch_v1.JobStatus.State.SUCCEEDED:
                return download_pickled_trial_with_values(bucket_name, result_blob_name)
            case batch_v1.JobStatus.State.FAILED:
                return None
            case _:
                await asyncio.sleep(10)


def build_job(
    config: Dict, bucket_name: str, blob_name: str, result_blob_name: str
) -> batch_v1.Job:

    runnable = batch_v1.Runnable()
    runnable.container = batch_v1.Runnable.Container()
    runnable.container.image_uri = "/".join(
        [
            f"{config['region']}-docker.pkg.dev",
            config["project_id"],
            config["repository"],
            f"{config['image_name_base']}-job:latest",
        ]
    )
    runnable.environment.variables = {
        "BUCKET_NAME": bucket_name,
        "BLOB_NAME": blob_name,
        "RESULT_BLOB_NAME": result_blob_name,
    }

    task = batch_v1.TaskSpec()
    task.runnables = [runnable]

    resources = batch_v1.ComputeResource()
    resources.cpu_milli = config["compute_resorce"]["cpu_milli"]
    resources.memory_mib = config["compute_resorce"]["memory_mib"]
    task.compute_resource = resources
    task.max_retry_count = 0
    group = batch_v1.TaskGroup()
    group.task_spec = task
    policy = batch_v1.AllocationPolicy.InstancePolicy()
    policy.machine_type = config["allocation_policy"]["machine_type"]
    policy.provisioning_model = config["allocation_policy"]["provisioning_model"]

    instances = batch_v1.AllocationPolicy.InstancePolicyOrTemplate()
    instances.policy = policy
    service_account = batch_v1.ServiceAccount()
    service_account.email = config["service_account"]
    allocation_policy = batch_v1.AllocationPolicy()
    allocation_policy.instances = [instances]
    allocation_policy.service_account = service_account

    job = batch_v1.Job()
    job.task_groups = [group]
    job.allocation_policy = allocation_policy
    job.logs_policy = batch_v1.LogsPolicy()
    job.logs_policy.destination = (
        batch_v1.LogsPolicy.Destination.CLOUD_LOGGING  # type: ignore
    )

    return job


async def create_batch_job(
    trial: optuna.Trial,
    config: Dict,
    client: batch_v1.BatchServiceClient,
    queue: asyncio.Queue,
):
    bucket_name = config["bucket_name"]
    blob_name = f"{trial.study.study_name}/trial_{trial.number}.pkl"
    result_blob_name = f"{trial.study.study_name}/trial_with_values_{trial.number}.pkl"
    upload_pickled_trial(trial, bucket_name, blob_name)

    job = build_job(config, bucket_name, blob_name, result_blob_name)

    create_request = batch_v1.CreateJobRequest()
    create_request.job = job
    create_request.job_id = f"job-{uuid4().hex}"
    create_request.parent = "/".join(
        [
            "projects",
            config["project_id"],
            "locations",
            config["region"],
        ]
    )
    job = client.create_job(create_request)
    job_result = await wait_for_job(job, bucket_name, result_blob_name)

    if job_result is not None:
        result = job_result
    else:
        result = TrialWithValues(trial, None)

    await queue.put(result)
    return result


def print_result(result: asyncio.Task[TrialWithValues]):
    r = result.result()
    trial = r.trial
    values = r.values

    print(
        f"Trial {r.trial.number} completed. The value is {values}. The best value is {trial.study.best_value} at trial {trial.study.best_trial.number} with parameters {json.dumps(trial.study.best_trial.params,indent=None)}"  # noqa: E501
    )


async def main():
    config = json.loads(os.environ["CONFIG"])
    bucket_name = config["bucket_name"]
    n_trials = config["n_trials"]
    n_jobs = config["n_jobs"]
    study = create_study()

    print(config)
    client = batch_v1.BatchServiceClient()
    queue = asyncio.Queue(n_jobs)
    tasks = set()

    for _ in range(n_jobs):
        trial = study.ask()
        task = asyncio.create_task(create_batch_job(trial, config, client, queue))
        tasks.add(task)
        task.add_done_callback(tasks.remove)
        task.add_done_callback(print_result)

    # for n_trials in range(n_trials - n_jobs):
    counter = 0
    while counter < n_trials:
        result = await queue.get()
        if result.values is not None:
            counter += 1
            study.tell(result.trial, result.values)
        else:
            study.tell(result.trial, state=optuna.trial.TrialState.FAIL)
        trial = study.ask()
        task = asyncio.create_task(create_batch_job(trial, config, client, queue))
        tasks.add(task)
        task.add_done_callback(tasks.remove)
        task.add_done_callback(print_result)
    while tasks:
        await asyncio.sleep(10)

    backup_trials(study, bucket_name)


if __name__ == "__main__":
    asyncio.run(main())
