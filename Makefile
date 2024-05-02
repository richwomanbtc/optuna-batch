SHELL := /bin/bash
.PHONY: build-optimizer build-job build push-optimizer push-job push update-container deploy run-optimizer

PROJECT_ID=$(shell yq eval '.project_id' config.yaml)
REGION=$(shell yq eval '.region' config.yaml)
ZONE=$(shell yq eval '.zone' config.yaml)
REPOSITORY=$(shell yq eval '.repository' config.yaml)
IMAGE_NAME_BASE=$(shell yq eval '.image_name_base' config.yaml)
INSTANCE_NAME=$(shell yq eval '.instance_name' config.yaml)
IMAGE_BASE=$(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(REPOSITORY)/$(IMAGE_NAME_BASE)

build-optimizer:
	docker build -t $(IMAGE_BASE)-optimizer -f Dockerfile.optimizer --platform linux/amd64 .

build-job:
	docker build -t $(IMAGE_BASE)-job -f Dockerfile.job  --platform linux/amd64 .

push-optimizer:
	docker push $(IMAGE_BASE)-optimizer

push-job:
	docker push $(IMAGE_BASE)-job

build: build-optimizer build-job

push: push-optimizer push-job

create-instance:
	gcloud compute instances create-with-container $(INSTANCE_NAME) \
    --project=$(PROJECT_ID) \
    --zone=$(ZONE) \
    --machine-type=e2-micro \
    --provisioning-model=STANDARD \
	--network-interface=network-tier=PREMIUM,subnet=default \
	--maintenance-policy=MIGRATE \
    --service-account=$(SERVICE_ACCOUNT) \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --image=projects/cos-cloud/global/images/cos-stable-113-18244-1-61 \
    --boot-disk-size=10GB \
	--boot-disk-type=pd-balanced \
    --boot-disk-device-name=$(INSTANCE_NAME) \
    --container-image=$(IMAGE_BASE)-optimizer \
    --container-restart-policy=always \
    --no-shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
	--metadata=google-logging-enabled=true,google-monitoring-enabled=true \
	--container-env-file <(echo CONFIG=`yq eval -o=json config.yaml | jq -c`)

update-container:
	gcloud compute instances update-container $(INSTANCE_NAME) --zone=$(ZONE) --container-image $(IMAGE_BASE)-optimizer --container-env-file <(echo CONFIG=`yq eval -o=json config.yaml | jq -c`)

deploy: build push update-container

run-optimizer:
	docker run --rm -it -v $(HOME)/.config/gcloud/:/root/.config/gcloud/ -e GOOGLE_CLOUD_PROJECT=$(PROJECT_ID) --env-file <(echo CONFIG=`yq eval -o=json config.yaml | jq -c`) $(IMAGE_BASE)-optimizer
