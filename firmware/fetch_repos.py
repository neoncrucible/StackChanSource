import json
import os
import subprocess
import sys


def apply_repo_patch(path, patch_path, required=False):
    patch_full_path = (
        patch_path
        if os.path.isabs(patch_path)
        else os.path.join(os.getcwd(), patch_path)
    )

    check_result = subprocess.run(
        ["git", "-C", path, "apply", "--check", patch_full_path]
    )
    if check_result.returncode == 0:
        subprocess.run(
            ["git", "-C", path, "apply", patch_full_path],
            check=True,
        )
        print(f"Applied patch {patch_path} to {path}")
        return

    reverse_check = subprocess.run(
        ["git", "-C", path, "apply", "--reverse", "--check", patch_full_path]
    )
    if reverse_check.returncode == 0:
        print(f"Patch {patch_path} is already applied to {path}")
        return

    message = f"Patch {patch_path} cannot be applied cleanly to {path}"
    if required:
        raise RuntimeError(message)
    print(f"{message}, skipped.")


def clone_or_update_repo(
    repo_url, path, ref=None, with_submodules=False, patches=None
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

    for patch in patches or []:
        if isinstance(patch, str):
            patch_path = patch
            required = False
        else:
            patch_path = patch["path"]
            required = patch.get("required", False)
        apply_repo_patch(path, patch_path, required)


def apply_project_source_overlays(script_dir):
    # Alpha 2 keeps the physically proven firmware source readable as the base
    # checkpoint. Narrow Project-owned additions are applied by guarded scripts
    # during each clean build, mirroring the pinned Windows runtime overlay model.
    overlays = [
        os.path.join(script_dir, "tools", "apply_m6_weather_display.py"),
        os.path.join(script_dir, "tools", "apply_m6_pixel_weather_display.py"),
    ]
    for overlay in overlays:
        if not os.path.isfile(overlay):
            raise RuntimeError(f"Required Kadence firmware overlay not found: {overlay}")
        subprocess.run([sys.executable, overlay], check=True)


def generate_kade_assets(script_dir):
    generator = os.path.join(script_dir, "tools", "generate_kade_assets.py")
    input_root = os.path.join(script_dir, "assets")
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
        patches = repo.get("patches")
        if patches is None and repo.get("patch"):
            patches = [repo["patch"]]

        resolved_patches = []
        for patch in patches or []:
            if isinstance(patch, str):
                resolved_patches.append(
                    patch if os.path.isabs(patch) else os.path.join(script_dir, patch)
                )
            else:
                resolved_patch = dict(patch)
                patch_path = resolved_patch["path"]
                resolved_patch["path"] = (
                    patch_path
                    if os.path.isabs(patch_path)
                    else os.path.join(script_dir, patch_path)
                )
                resolved_patches.append(resolved_patch)

        clone_or_update_repo(
            repo["url"],
            repo_path,
            branch,
            with_submodules,
            resolved_patches,
        )

    apply_project_source_overlays(script_dir)
    generate_kade_assets(script_dir)


if __name__ == "__main__":
    fetch_dependencies()
