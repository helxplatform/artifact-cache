import logging
import shutil

from urllib.parse import urlparse
from pathlib import Path
from git import Repo, RemoteReference

logger = logging.getLogger(__name__)

def parse_repo_name(repo_or_url: Repo | str) -> str:
    if isinstance(repo_or_url, Repo):
        # Repository instance
        if not repo_or_url.bare:
            return Path(repo_or_url.working_tree_dir).stem
        else:
            return Path(repo_or_url.git_dir).stem
    else:
        # URL
        return Path(urlparse(repo_or_url).path).stem

def clone_repo(repo_url: str, clone_dir: Path) -> Repo:
    if clone_dir.exists():
        logger.warning(f"Repository already exists at '{ clone_dir }'. Overwriting...")
        shutil.rmtree(clone_dir)
    
    logger.info(f"Cloning repository from '{ repo_url }' to '{ clone_dir }'.")
    return Repo.clone_from(repo_url, clone_dir)

def fetch_remote_branches(repo: Repo) -> None:
    remote = repo.remote()
    remote.fetch()

def copy_repo_branch(repo: Repo, branch_ref: RemoteReference, output_dir: Path) -> None:
    remote = repo.remote()
    branch_name = branch_ref.name.replace(f"{ remote.name }/", "")
    if branch_name == "HEAD": return

    repo_root = Path(repo.working_tree_dir) if repo.working_tree_dir is not None else None
    if repo_root is None:
        # Repository is bare.
        return

    repo.git.checkout(branch_ref)
    
    # Prepare branch directory
    branch_dest = output_dir / branch_name
    logger.info(f"Copying '{ branch_name }' to assets under '{ branch_dest }'.")
    if branch_dest.exists():
        logger.warning(f"Branch already exists in assets under '{ branch_dest }'. Overwriting...")
        shutil.rmtree(branch_dest)
    branch_dest.mkdir(parents=True)

    for item_path in repo_root.iterdir():
        if item_path.name == ".git":
            continue
        
        src = repo_root / item_path.name
        dest = branch_dest / item_path.name
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)

def copy_repo_branches(repo: Repo, output_dir: Path) -> None:
    # Ensure that branch refs have been fetched for the remote.
    fetch_remote_branches(repo)

    # Ensure the asset destination exists.
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if repo.bare:
        logger.error(f"Repository '{ parse_repo_name(repo) }' is bare and lacks a root. No files to clone, skipping...")
        return
    
    for ref in repo.remote().refs:
        copy_repo_branch(repo, ref, output_dir)