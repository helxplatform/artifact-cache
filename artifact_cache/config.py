import os
import logging

from pathlib import Path

REPO_BASE_PATH = Path(os.environ.get("REPO_BASE_PATH", "./git-repos"))
EXPORT_BASE_PATH = Path(os.environ.get("EXPORT_BASE_PATH", "./assets"))
REPO_TARGETS = [url.strip() for url in os.environ["REPO_TARGETS"].split(",") if url.strip()]

PVC_NAME = os.environ.get("PVC_NAME")
PVC_ENABLED = PVC_NAME is not None and PVC_NAME != ""
PVC_MOUNT_PATH = Path("/mnt")
PVC_EXPORT_PATH = PVC_MOUNT_PATH / EXPORT_BASE_PATH
NAMESPACE = os.environ["NAMESPACE"]

STATIC_RESOURCE_PATH = os.environ.get("STATIC_RESOURCE_PATH")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[ logging.StreamHandler() ]
)