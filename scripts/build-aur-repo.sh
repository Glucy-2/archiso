#!/usr/bin/env bash
# Build every package in aur-packages.txt and assemble them into a pacman
# repository named "repo". A package with packages/<name>/PKGBUILD in this
# project is built from that directory; otherwise the latest AUR version is used.
#
# Usage: scripts/build-aur-repo.sh [OUTPUT_DIR]   (default: <project>/repo)
#
# Requires an Arch Linux environment with base-devel, git and sudo.
# Missing build dependencies are installed with pacman (via makepkg -s).
# When run as root (e.g. in a container) it re-executes itself as an
# unprivileged "builder" user, because makepkg refuses to run as root.
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="$(realpath -m -- "${1:-$project_dir/repo}")"
list_file="$project_dir/aur-packages.txt"

if [[ $EUID -eq 0 ]]; then
    id builder &>/dev/null || useradd --create-home builder
    echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder
    chmod 0440 /etc/sudoers.d/builder
    install -d -o builder -g builder -- "$out_dir"
    exec runuser -u builder -- "$0" "$out_dir"
fi

mapfile -t packages < <(sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "$list_file")
((${#packages[@]})) || { echo "no packages listed in $list_file" >&2; exit 1; }

work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT

# Uncompressed packages: the ISO's erofs image compresses them anyway.
export PKGEXT='.pkg.tar'
export PKGDEST="$work_dir/pkgs"
mkdir -p "$PKGDEST"

for pkg in "${packages[@]}"; do
    echo "::group::$pkg"
    if [[ -f $project_dir/packages/$pkg/PKGBUILD ]]; then
        cp -r -- "$project_dir/packages/$pkg" "$work_dir/$pkg"
    else
        git clone --depth 1 "https://aur.archlinux.org/${pkg}.git" "$work_dir/$pkg"
    fi
    (cd "$work_dir/$pkg" && makepkg --syncdeps --noconfirm --needed --cleanbuild)
    echo "::endgroup::"
done

# Replace the repository wholesale so stale versions are dropped.
find "$out_dir" -mindepth 1 -delete
# makepkg also emits <name>-debug packages; they are not wanted in the ISO repo.
for f in "$PKGDEST"/*.pkg.tar; do
    [[ $f == *-debug-* ]] || cp -- "$f" "$out_dir/"
done
repo-add --new "$out_dir/repo.db.tar.zst" "$out_dir"/*.pkg.tar
echo "Repository written to $out_dir"
