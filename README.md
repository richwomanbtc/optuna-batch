# Optuna Cloud Batch Template

This is a template repository for running Optuna optimization on Google Cloud Batch and GCS.

## Requirements
- `python>=3.11`
- `docker`
- `make`
- `yq`
- `gcloud`

## How to use

1. Create two service accounts, SA1 and SA2. SA1 is for optimizer and SA2 is for job batches. Add permissions `Storage Object User`, `Batch Job Editor`, `Artifact Registry Reader` and `Logs Writer` to a service account for SA1 and `Storage Object User`, `Artifact Registry Reader` and `Logs Writer` for SA2.
1. Edit `optunabatch/custom.py` to define your objective function and study settings.
1. Edit `config.yaml` to define your cloud batch settings. Service account for the job instances (SA2) should be specified in `service_account` field.
1. `make build` to build the Docker images.
1. `make push` to push the Docker images to the Artifact Resigtry.
1. Create a GCE instance. You can use `make create-instance SERVICE_ACCOUNT={SA1}` to create a VM. The service account should have permissions for `Storage Object User`, `Batch Job Editor` and `Logs Writer`.
1. `make update-container` to deploy the Docker images to the GCP.
1. Trials will be stored in the GCS bucket specified in `config.yaml`.

The command `make run-optimizer` is for debugging in the local environment. Note that it uses credentials stored in `~/.config/gcloud/`.



## References
- [Run basic job with Cloud Batch](https://cloud.google.com/batch/docs/create-run-basic-job)
- [Optuna](https://optuna.org/)