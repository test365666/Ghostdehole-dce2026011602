import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pyzipper
import requests


def log(message):
    print(message, flush=True)


def update_status(message):
    status_url = os.environ.get("DCE_STATUS_URL", "")
    uuid = os.environ.get("DCE_UUID", "")
    if not status_url or not uuid:
        return
    try:
        requests.post(status_url, json={"uuid": uuid, "status": message}, timeout=5)
    except Exception as exc:
        log(f"status update failed: {exc}")


def run(cmd, cwd=None, check=True):
    log(f"run: {' '.join(str(part) for part in cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check)


def replace_in_file(path, old, new, required=False):
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return False
    data = path.read_text(encoding="utf-8", errors="surrogateescape")
    if old not in data:
        if required:
            raise ValueError(f"missing '{old}' in {path}")
        return False
    path.write_text(data.replace(old, new), encoding="utf-8", errors="surrogateescape")
    return True


def apply_patch_if_needed(worktree, patch_path, required=False):
    check = subprocess.run(
        ["git", "-C", str(worktree), "apply", "--check", str(patch_path)],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        run(["git", "-C", str(worktree), "apply", str(patch_path)])
        return True
    reverse = subprocess.run(
        ["git", "-C", str(worktree), "apply", "--reverse", "--check", str(patch_path)],
        capture_output=True,
        text=True,
    )
    if reverse.returncode == 0:
        log(f"patch already applied: {patch_path.name}")
        return False
    if required:
        raise RuntimeError(f"failed to apply patch: {patch_path.name}\n{check.stderr}")
    log(f"patch skipped: {patch_path.name}\n{check.stderr}")
    return False


def resolve_git_ref(repo, version):
    def has_ref(ref):
        return subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", ref],
            capture_output=True,
        ).returncode == 0

    if version == "master":
        for ref in ("refs/remotes/origin/master", "refs/heads/master", "HEAD"):
            if has_ref(ref):
                return ref
        return "HEAD"

    tag_ref = f"refs/tags/{version}"
    if not has_ref(tag_ref):
        subprocess.run(["git", "-C", str(repo), "fetch", "--tags"], check=False)
    if has_ref(tag_ref):
        return tag_ref
    return "HEAD"


def remove_update_block(path):
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
    output = []
    in_block = False
    for line in lines:
        if "let (request, url) =" in line:
            in_block = True
            continue
        if in_block:
            if "Ok(())" in line:
                output.append(line)
                in_block = False
            continue
        output.append(line)
    path.write_text("\n".join(output) + "\n", encoding="utf-8", errors="surrogateescape")


def main():
    dce_root = Path(os.environ.get("DCE_ROOT", ".")).resolve()
    zip_path = Path(os.environ.get("DCE_ZIP_PATH", "")).resolve()
    uuid = os.environ.get("DCE_UUID", "")
    filename = os.environ.get("DCE_FILENAME", "rustdesk")
    platform = os.environ.get("DCE_PLATFORM", "windows")
    output_dir = Path(os.environ.get("DCE_OUTPUT_DIR", dce_root / "exe" / uuid)).resolve()
    zip_password = os.environ.get("ZIP_PASSWORD", "")
    rustdesk_src = Path(os.environ.get("RUSTDESK_SRC", "")).resolve()

    update_status("local build started")

    if platform != "windows":
        update_status("local build supports windows only")
        sys.exit(1)

    if not zip_path.exists():
        update_status("zip not found")
        sys.exit(1)

    if not zip_password:
        update_status("ZIP_PASSWORD missing")
        sys.exit(1)

    if not rustdesk_src.exists():
        update_status("RUSTDESK_SRC missing")
        sys.exit(1)

    if not shutil.which("git"):
        update_status("git not found")
        sys.exit(1)

    update_status("decrypting config")
    try:
        with pyzipper.AESZipFile(zip_path) as zf:
            zf.setpassword(zip_password.encode())
            with zf.open("secrets.json") as handle:
                secrets = json.load(handle)
    except Exception as exc:
        update_status(f"zip decrypt failed: {exc}")
        sys.exit(1)

    version = secrets.get("version", "master")
    server = secrets.get("server", "rs-ny.rustdesk.com")
    key = secrets.get("key", "OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=")
    api_server = secrets.get("apiServer", "https://admin.rustdesk.com")
    custom_b64 = secrets.get("custom", "")
    appname = secrets.get("appname", "rustdesk")
    url_link = secrets.get("urlLink", "https://rustdesk.com")
    download_link = secrets.get("downloadLink", "https://rustdesk.com/download")
    delay_fix = secrets.get("delayFix", "false") == "true"
    cycle_monitor = secrets.get("cycleMonitor", "false") == "true"
    x_offline = secrets.get("xOffline", "false") == "true"
    remove_new_version = secrets.get("removeNewVersionNotif", "false") == "true"
    compname = secrets.get("compname", "Purslane Ltd")

    update_status("preparing source")
    worktree_root = Path(os.environ.get("LOCAL_BUILD_WORKTREE_ROOT", "")).resolve()
    if not str(worktree_root) or str(worktree_root) == ".":
        worktree_root = dce_root / "local_builds"
    worktree_root.mkdir(parents=True, exist_ok=True)
    worktree_dir = worktree_root / uuid

    if worktree_dir.exists():
        update_status("worktree already exists")
        sys.exit(1)

    ref = resolve_git_ref(rustdesk_src, version)
    run(["git", "-C", str(rustdesk_src), "worktree", "add", "--detach", str(worktree_dir), ref])

    update_status("applying patches")
    allow_custom = dce_root / ".github" / "patches" / "allowCustom.py"
    if not allow_custom.exists():
        update_status("allowCustom.py missing")
        sys.exit(1)
    run([sys.executable, str(allow_custom)], cwd=worktree_dir)

    remove_setup = dce_root / ".github" / "patches" / "removeSetupServerTip.diff"
    apply_patch_if_needed(worktree_dir, remove_setup, required=False)

    if cycle_monitor:
        apply_patch_if_needed(worktree_dir, dce_root / ".github" / "patches" / "cycle_monitor.diff", required=False)
    if x_offline:
        apply_patch_if_needed(worktree_dir, dce_root / ".github" / "patches" / "xoffline.diff", required=False)

    replace_in_file(worktree_dir / "libs" / "hbb_common" / "src" / "config.rs", "rs-ny.rustdesk.com", server, required=True)
    replace_in_file(worktree_dir / "libs" / "hbb_common" / "src" / "config.rs", "OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=", key, required=True)
    replace_in_file(worktree_dir / "src" / "common.rs", "https://admin.rustdesk.com", api_server, required=False)

    if delay_fix:
        replace_in_file(worktree_dir / "src" / "client.rs", "!key.is_empty()", "false", required=False)

    if remove_new_version:
        replace_in_file(worktree_dir / "flutter" / "lib" / "desktop" / "pages" / "desktop_home_page.dart", "updateUrl.isNotEmpty", "false", required=False)
        remove_update_block(worktree_dir / "src" / "common.rs")

    if url_link != "https://rustdesk.com":
        replace_in_file(worktree_dir / "build.py", "Homepage: https://rustdesk.com", f"Homepage: {url_link}", required=False)
        replace_in_file(worktree_dir / "flutter" / "lib" / "common.dart", "launchUrl(Uri.parse('https://rustdesk.com'));", f"launchUrl(Uri.parse('{url_link}'));", required=False)
        replace_in_file(worktree_dir / "flutter" / "lib" / "desktop" / "pages" / "desktop_setting_page.dart", "launchUrlString('https://rustdesk.com');", f"launchUrlString('{url_link}');", required=False)
        replace_in_file(worktree_dir / "flutter" / "lib" / "desktop" / "pages" / "desktop_setting_page.dart", "launchUrlString('https://rustdesk.com/privacy.html')", f"launchUrlString('{url_link}/privacy.html')", required=False)
        replace_in_file(worktree_dir / "flutter" / "lib" / "mobile" / "pages" / "settings_page.dart", "const url = 'https://rustdesk.com/';", f\"const url = '{url_link}';\", required=False)
        replace_in_file(worktree_dir / "flutter" / "lib" / "mobile" / "pages" / "settings_page.dart", "launchUrlString('https://rustdesk.com/privacy.html')", f"launchUrlString('{url_link}/privacy.html')", required=False)
        replace_in_file(worktree_dir / "flutter" / "lib" / "desktop" / "pages" / "install_page.dart", "https://rustdesk.com/privacy.html", f"{url_link}/privacy.html", required=False)

    if download_link != "https://rustdesk.com/download":
        replace_in_file(worktree_dir / "flutter" / "lib" / "desktop" / "pages" / "desktop_home_page.dart", "https://rustdesk.com/download", download_link, required=False)
        replace_in_file(worktree_dir / "flutter" / "lib" / "mobile" / "pages" / "connection_page.dart", "https://rustdesk.com/download", download_link, required=False)
        replace_in_file(worktree_dir / "src" / "ui" / "index.tis", "https://rustdesk.com/download", download_link, required=False)

    if appname and appname.lower() != "rustdesk":
        replace_in_file(worktree_dir / "Cargo.toml", "description = \"RustDesk Remote Desktop\"", f"description = \"{appname}\"", required=False)
        replace_in_file(worktree_dir / "Cargo.toml", "ProductName = \"RustDesk\"", f"ProductName = \"{appname}\"", required=False)
        replace_in_file(worktree_dir / "Cargo.toml", "FileDescription = \"RustDesk Remote Desktop\"", f"FileDescription = \"{appname}\"", required=False)
        replace_in_file(worktree_dir / "Cargo.toml", "OriginalFilename = \"rustdesk.exe\"", f"OriginalFilename = \"{appname}.exe\"", required=False)
        replace_in_file(worktree_dir / "libs" / "portable" / "Cargo.toml", "description = \"RustDesk Remote Desktop\"", f"description = \"{appname}\"", required=False)
        replace_in_file(worktree_dir / "libs" / "portable" / "Cargo.toml", "ProductName = \"RustDesk\"", f"ProductName = \"{appname}\"", required=False)
        replace_in_file(worktree_dir / "libs" / "portable" / "Cargo.toml", "FileDescription = \"RustDesk Remote Desktop\"", f"FileDescription = \"{appname}\"", required=False)
        replace_in_file(worktree_dir / "libs" / "portable" / "Cargo.toml", "OriginalFilename = \"rustdesk.exe\"", f"OriginalFilename = \"{appname}.exe\"", required=False)
        replace_in_file(worktree_dir / "flutter" / "windows" / "runner" / "Runner.rc", "\"RustDesk Remote Desktop\"", f"\"{appname}\"", required=False)
        replace_in_file(worktree_dir / "flutter" / "windows" / "runner" / "Runner.rc", "\"rustdesk.exe\"", f"\"{filename}.exe\"", required=False)
        replace_in_file(worktree_dir / "flutter" / "windows" / "runner" / "Runner.rc", "\"RustDesk\"", f"\"{appname}\"", required=False)
        lang_dir = worktree_dir / "src" / "lang"
        if lang_dir.exists():
            for lang_file in lang_dir.rglob("*.rs"):
                replace_in_file(lang_file, "RustDesk", appname, required=False)

    if compname and compname != "Purslane Ltd":
        replace_in_file(worktree_dir / "flutter" / "lib" / "desktop" / "pages" / "desktop_setting_page.dart", "Purslane Ltd", compname, required=False)
        replace_in_file(worktree_dir / "res" / "msi" / "preprocess.py", "Purslane Ltd", compname, required=False)
        replace_in_file(worktree_dir / "res" / "msi" / "preprocess.py", "PURSLANE", compname, required=False)
        replace_in_file(worktree_dir / "flutter" / "windows" / "runner" / "Runner.rc", "Purslane Ltd", compname, required=False)
        replace_in_file(worktree_dir / "Cargo.toml", "Purslane Ltd", compname, required=False)
        replace_in_file(worktree_dir / "libs" / "portable" / "Cargo.toml", "Purslane Ltd", compname, required=False)

    icon_path = dce_root / "png" / uuid / "icon.png"
    if icon_path.exists():
        res_dir = worktree_dir / "res"
        res_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon_path, res_dir / "icon.png")
        magick = shutil.which("magick")
        if magick:
            run([magick, str(res_dir / "icon.png"), "-define", "icon:auto-resize=256,64,48,32,16", str(res_dir / "icon.ico")])
            shutil.copyfile(res_dir / "icon.ico", res_dir / "tray-icon.ico")
            run([magick, str(res_dir / "icon.png"), "-resize", "32x32", str(res_dir / "32x32.png")])
            run([magick, str(res_dir / "icon.png"), "-resize", "64x64", str(res_dir / "64x64.png")])
            run([magick, str(res_dir / "icon.png"), "-resize", "128x128", str(res_dir / "128x128.png")])
            run([magick, str(res_dir / "128x128.png"), "-resize", "200%", str(res_dir / "128x128@2x.png")])
        flutter = shutil.which("flutter")
        if flutter:
            run([flutter, "pub", "get"], cwd=worktree_dir / "flutter")
            run([flutter, "pub", "run", "flutter_launcher_icons"], cwd=worktree_dir / "flutter")

    update_status("building rustdesk")
    run([sys.executable, "build.py", "--portable", "--hwcodec", "--flutter", "--vram", "--skip-portable-pack"], cwd=worktree_dir)

    release_dir = worktree_dir / "flutter" / "build" / "windows" / "x64" / "runner" / "Release"
    if not release_dir.exists():
        update_status("build output missing")
        sys.exit(1)

    rustdesk_dir = worktree_dir / "rustdesk"
    if rustdesk_dir.exists():
        update_status("rustdesk output already exists")
        sys.exit(1)
    shutil.move(str(release_dir), str(rustdesk_dir))

    if icon_path.exists() and shutil.which("magick"):
        assets_dir = rustdesk_dir / "data" / "flutter_assets" / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        run(["magick", str(icon_path), str(assets_dir / "icon.svg")])

    logo_path = dce_root / "png" / uuid / "logo.png"
    if logo_path.exists():
        assets_dir = rustdesk_dir / "data" / "flutter_assets" / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(logo_path, assets_dir / "logo.png")

    if custom_b64:
        (rustdesk_dir / "custom_.txt").write_text(custom_b64, encoding="ascii")

    app_exe = rustdesk_dir / "rustdesk.exe"
    if app_exe.exists():
        app_exe.rename(rustdesk_dir / f"{appname}.exe")

    update_status("packaging exe")
    portable_dir = worktree_dir / "libs" / "portable"
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=portable_dir)
    run([sys.executable, "generate.py", "-f", str(rustdesk_dir), "-o", ".", "-e", str(rustdesk_dir / f"{appname}.exe")], cwd=portable_dir)

    packer_exe = portable_dir / "target" / "release" / "rustdesk-portable-packer.exe"
    if not packer_exe.exists():
        update_status("portable packer missing")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(packer_exe, output_dir / f"{filename}.exe")

    if zip_path.exists():
        zip_path.unlink()

    update_status("success")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        update_status(f"failed: {exc}")
        raise
