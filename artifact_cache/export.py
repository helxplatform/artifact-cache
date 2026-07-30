import logging
import time
import subprocess
import tarfile

from pathlib import Path
from io import BytesIO
from kubernetes import client, stream
from kubernetes.client.exceptions import ApiException
from .k8s import core_v1
from .git import clone_repo, copy_repo_branches, parse_repo_name
from . import config

logger = logging.getLogger(__name__)

def instantiate_pvc(pvc_name: str, namespace: str) -> None:
    try:
        # PVC already exists
        core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
        return
    except ApiException as e:
        if e.status != 404:
            raise

    logger.info(f"Creating PVC '{ pvc_name }'.")
    pvc_spec = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(name=pvc_name),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteMany"],
            resources=client.V1ResourceRequirements(
                requests={"storage": "2Gi"}
            )
        )
    )
    res = core_v1.create_namespaced_persistent_volume_claim(body=pvc_spec, namespace=namespace)

def export_repositories(repo_urls: list[str], repo_path: Path, export_base_path: Path) -> None:
    for repo_url in repo_urls:
        repo_name = parse_repo_name(repo_url)
        repo_path = repo_path / repo_name
        export_path = export_base_path / repo_name
        logger.info(f"Exporting repository '{ repo_name }'.")
        repo = clone_repo(repo_url, repo_path)
        copy_repo_branches(repo, export_path)

def create_mount_pod(pvc_name: str, namespace: str, mount_path: Path) -> tuple[str, str]:
    logger.info(f"Creating temporary mount pod for importing data into '{ pvc_name }'.")

    pod_name = f"{ pvc_name }-data-import"
    container_name = f"{ pvc_name }-import-container"
    pod_spec = client.V1Pod(
        metadata=client.V1ObjectMeta(name=pod_name),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name=container_name,
                    image="busybox",
                    image_pull_policy="IfNotPresent",
                    command=["tail", "-f", "/dev/null"],
                    volume_mounts=[client.V1VolumeMount(
                        mount_path=str(mount_path),
                        name=pvc_name
                    )]
                )
            ],
            volumes=[
                client.V1Volume(
                    name=pvc_name,
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    )
                )
            ],
            restart_policy="Never"
        )
    )
    try:
        core_v1.create_namespaced_pod(body=pod_spec, namespace=namespace)
    except ApiException as e:
        if e.status == 409:
            logger.warning("Data import pod already exists. Proceeding...")
        else:
            raise
    
    return pod_name, container_name

def teardown_mount_pod(pod_name: str, namespace: str) -> None:
    logger.info(f"Deleting data import pod '{ pod_name }'.")
    try:
        core_v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Error deleting data import pod: { e }")

def wait_for_pod_ready(pod_name: str, namespace: str, timeout: int=60) -> None:
    logger.info(f"Waiting for pod '{ pod_name }' to be running...")
    for i in range(timeout):
        pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        if pod.status.phase == "Running":
            return
        time.sleep(1)
    raise TimeoutError(f"Pod '{ pod_name}' did not become ready within { timeout } seconds.")

def create_tar_archive(src: Path) -> BytesIO:
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        for path in src.rglob("*"):
            archive_name = path.relative_to(src)
            tar.add(str(path), arcname=str(archive_name))
    tar_stream.seek(0)
    return tar_stream

"""
def copy_directory_to_mount(pod_name: str, container_name: str, namespace: str, src: Path, dest: Path) -> None:
    logger.info(f"Copying directory '{ src }' to pod '{ pod_name }:{ dest }'. This may take a while...")

    tar_stream = create_tar_archive(src)
    
    resp = stream.stream(
        core_v1.connect_get_namespaced_pod_exec,
        pod_name,
        namespace,
        container=container_name,
        command=["/bin/sh", "-c", f"mkdir -p { dest } && tar -xf - -C { dest }"],
        stderr=True,
        stdin=True,
        stdout=True,
        tty=False,
        _preload_content=False
    )

    chunk_size = 1024 * 1024 # 1 MB
    while True:
        chunk = tar_stream.read(chunk_size)
        if not chunk:
            break
        resp.write_stdin(chunk)

    # Close stdin
    resp.write_stdin("")

    while resp.is_open():
        resp.update(timeout=1)
        if resp.peek_stdout():
            logger.info(f"'{ pod_name }' STDOUT: { resp.read_stdout() }")
        if resp.peek_stderr():
            logger.warning(f"'{ pod_name }' STDERR: { resp.read_stderr() }")
    resp.close()

    logger.info(f"Successfully copied '{ src }' into '{ dest }' on PVC.")
"""

def copy_directory_to_mount(pod_name: str, container_name: str, namespace: str, src: Path, dest: Path, retries: int=5) -> None:
    logger.info(f"Copying directory '{ src }' to pod '{ pod_name }:{ dest }'. This may take a while...")

    cmd = [
        "kubectl", "cp",
        str(src),
        f"{ namespace }/{ pod_name }:{ str(dest) }",
        f"--retries={ retries }"
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        error_msg = f"""
Command failed!

Command: {' '.join(e.cmd)}
Exit code: {e.returncode}

--- STDOUT ---
{e.stdout.strip() or '[no output]'}

--- STDERR ---
{e.stderr.strip() or '[no output]'}
""".strip()
        raise RuntimeError(error_msg) from e

    logger.info(f"Successfully copied '{ src }' into '{ dest }' on PVC.")

def export_to_pvc(pvc_name: str, namespace: str, mount_path: Path, src: Path, dest: Path) -> None:
    mount_pod, mount_container = create_mount_pod(pvc_name, namespace, mount_path)
    try:
        wait_for_pod_ready(mount_pod, namespace)
        copy_directory_to_mount(mount_pod, mount_container, namespace, src, dest)
    finally:
        teardown_mount_pod(mount_pod, namespace)

if __name__ == "__main__":
    export_repositories(config.REPO_TARGETS, config.REPO_BASE_PATH, config.EXPORT_BASE_PATH)
    if config.PVC_ENABLED:
        instantiate_pvc(config.PVC_NAME, config.NAMESPACE)
        export_to_pvc(
            config.PVC_NAME,
            config.NAMESPACE,
            config.PVC_MOUNT_PATH,
            config.EXPORT_BASE_PATH,
            config.PVC_EXPORT_PATH
        )