from kubernetes import client, config

config.load_kube_config()

core_v1 = client.CoreV1Api()