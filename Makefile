PYTHON           := /usr/bin/env python3
SHELL 			 := /bin/bash
BRANCH_NAME	 	 := $(shell git branch --show-current | sed -r 's/[/]+/_/g')
override VERSION := ${BRANCH_NAME}-${VER}
DOCKER_ORG   	 := containers.renci.org/helxplatform
DOCKER_TAG   	 := artifact-cache:${VERSION}

.DEFAULT_GOAL = help

.PHONY: help install archive serve build publish

#help: List available tasks on this project
help:
	@grep -E '^#[a-zA-Z\.\-]+:.*$$' $(MAKEFILE_LIST) | tr -d '#' | awk 'BEGIN {FS = ": "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

#install: Install application along with required development packages
install:
	${PYTHON} -m pip install -r requirements.txt

archive:
	${PYTHON} -m artifact_cache.export

serve:
	${PYTHON} -m http.server 8080 --bind 0.0.0.0 --directory $(STATIC_RESOURCE_PATH)

#build: build project docker image
build:
	if [ -z "$(VER)" ]; then echo "Please provide a value for the VER variable like this:"; echo "make VER=4 build"; false; fi;
	echo "Building docker image: $(DOCKER_TAG)"
	docker build --platform=linux/amd64 . --no-cache --pull -t $(DOCKER_ORG)/$(DOCKER_TAG)

#publish: push all artifacts to registries
publish: build
	if [ -z "$(VER)" ]; then echo "Please provide a value for the VER variable like this:"; echo "make VER=4 build"; false; fi;
	docker image push $(DOCKER_ORG)/$(DOCKER_TAG)