import json
import os
import subprocess
import sys


def clone_or_update_repo(
    repo_url, path, ref=None, with_submodules=False, patch_path=None
):
    if not os.path.exists(path):
        subprocess.run(["git", "clone", repo_url, path], check=True)
    else:
        subprocess.run(["git", "-C", path, "fetch"], check=True)

    if ref:
        subprocess.run(["git", "-C", path, "checkout", ref], check=True)

    if with_submodules:
        subprocess.run(
            ["git", "-C", path, "submodule", "update", "--init", "--recursive"],
            check=True,
        )

    # Apply the factory dependency patch only when it still applies cleanly.
    if patch_path:
        patch_full_path = (
            patch_path
            if os.path.isabs(patch_path)
            else os.path.join(os.getcwd(), patch_path)
        )
        check_result = subprocess.run(
            ["git", "-C", path, "apply", "--check", patch_full_path]
        )
        if check_result.returncode == 0:
            subprocess.run(["git", "-C", path, "apply", patch_full_path], check=True)
            print(f"Applied patch {patch_path} to {path}")
        else:
            print(f"Patch {patch_path} cannot be applied cleanly to {path}, skipped.")


def generate_kade_assets(script_dir):
    generator = os.path.join(script_dir, "tools", "generate_kade_assets.py")
    input_root = os.path.join(script_dir, "assets-source")
    output = os.path.join(script_dir, "main", "kade_assets_generated.h")
    subprocess.run(
        [
            sys.executable,
            generator,
            "--input-root",
            input_root,
            "--output",
            output,
        ],
        check=True,
    )


def fetch_dependencies():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "repos.json")

    with open(config_path, encoding="utf-8") as file:
        repos = json.load(file)

    for repo in repos:
        repo_path = os.path.join(script_dir, repo["path"])
        branch = repo.get("branch")
        with_submodules = repo.get("with_submodules", False)
        patch = repo.get("patch")
        if patch and not os.path.isabs(patch):
            patch = os.path.join(script_dir, patch)
        clone_or_update_repo(repo["url"], repo_path, branch, with_submodules, patch)

    generate_kade_assets(script_dir)


if __name__ == "__main__":
    fetch_dependencies()
