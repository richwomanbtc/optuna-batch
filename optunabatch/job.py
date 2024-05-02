import os
import pickle
from dataclasses import dataclass
from typing import Callable, Sequence

import optuna
from custom import objective  # type: ignore
from google.cloud import storage  # type: ignore

ObjectiveValueType = float | Sequence[float] | None


@dataclass
class TrialWithValues:
    trial: optuna.Trial
    values: ObjectiveValueType


def upload_pickled_trial_with_values(
    trial_with_values: TrialWithValues, bucket_name: str, blob_name: str
):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pickle.dumps(trial_with_values))


def download_pickled_trial(bucket_name: str, blob_name: str) -> optuna.Trial:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return pickle.loads(blob.download_as_string())


def run_objective(
    objective: Callable[[optuna.trial.BaseTrial], ObjectiveValueType],
    bucket_name: str,
    blob_name: str,
    result_blob_name: str,
):
    trial = download_pickled_trial(bucket_name=bucket_name, blob_name=blob_name)
    print(f"Running objective with trial: {trial}")
    print(f"{trial.study.trials=}")
    objective_value = objective(trial)
    result = TrialWithValues(trial=trial, values=objective_value)
    upload_pickled_trial_with_values(
        result, bucket_name=bucket_name, blob_name=result_blob_name
    )


if __name__ == "__main__":
    bucket_name = os.environ["BUCKET_NAME"]
    blob_name = os.environ["BLOB_NAME"]
    result_blob_name = os.environ["RESULT_BLOB_NAME"]
    run_objective(
        objective=objective,
        bucket_name=bucket_name,
        blob_name=blob_name,
        result_blob_name=result_blob_name,
    )
