#!/usr/bin/env bash
# Build one ISO profile inside a clean, privileged Arch Linux container (CI).
#
# Usage: scripts/build-iso.sh PROFILE
#
# The profiles' pacman.conf points the [repo] repository at
# file:///home/glucy2/Documents/archiso/repo, so the project directory MUST be
# mounted at /home/glucy2/Documents/archiso. The repo must already be built
# (scripts/build-aur-repo.sh). The ISO is written to <project>/out.
set -euo pipefail

profile="${1:?usage: $0 PROFILE}"
project_dir=/home/glucy2/Documents/archiso
[[ -d $project_dir/$profile ]] || { echo "no such profile: $profile" >&2; exit 1; }
[[ -f $project_dir/repo/repo.db.tar.zst ]] || { echo "repo/ not built" >&2; exit 1; }

# repo-add's repo.db/repo.files symlinks do not survive artifact transfer.
ln -sf repo.db.tar.zst "$project_dir/repo/repo.db"
ln -sf repo.files.tar.zst "$project_dir/repo/repo.files"

# [archlinuxcn] is referenced by the profiles' pacman.conf.
cat > /etc/pacman.d/mirrorlist-archlinuxcn <<'EOF'
Server = https://repo.archlinuxcn.org/$arch
Server = https://ipv4.mirrors.ustc.edu.cn/archlinuxcn/$arch
Server = https://fast-mirror.isrc.ac.cn/archlinuxcn/$arch
EOF
pacman-key --init
pacman-key --populate archlinux

# Bootstrap trust for archlinuxcn: fetch its keyring from a throwaway config.
mkdir -p /tmp/cn-db
cat > /tmp/cn-bootstrap.conf <<'EOF'
[options]
Architecture = auto
[archlinuxcn]
SigLevel = Never
Include = /etc/pacman.d/mirrorlist-archlinuxcn
EOF
pacman --config /tmp/cn-bootstrap.conf --dbpath /tmp/cn-db --noconfirm -Sydd archlinuxcn-keyring
pacman-key --populate archlinuxcn

pacman --noconfirm -Syu --needed archiso grub

mkarchiso -v -w /tmp/archiso-work -o "$project_dir/out" "$project_dir/$profile"
