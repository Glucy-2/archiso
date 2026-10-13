# archiso

Custom Arch Linux live ISO profiles, built automatically by GitHub Actions.

## Layout

| Path | Purpose |
| --- | --- |
| `glucy2-standard/` | archiso profile: standard image |
| `glucy2-gpu/` | archiso profile: standard + GPU/compute stack (large, ~8 GB ISO) |
| `aur-packages.txt` | Packages built into the local `repo` pacman repository |
| `packages/<name>/` | Custom PKGBUILD directory; overrides the AUR version of `<name>` |
| `scripts/build-aur-repo.sh` | Builds the packages in `aur-packages.txt` into a pacman repo |
| `scripts/build-iso.sh` | Builds one profile with `mkarchiso` inside an Arch container |
| `.github/workflows/build.yml` | CI workflow |

## CI

`.github/workflows/build.yml` runs every Monday 03:00 UTC and on manual dispatch (`workflow_dispatch`).

1. `repo` job: builds every package in `aur-packages.txt` (latest AUR PKGBUILD, or `packages/<name>/PKGBUILD` if present) and uploads `repo/` as an artifact.
2. `iso` job (matrix: both profiles): downloads the repo artifact, runs `scripts/build-iso.sh <profile>` in a privileged Arch container, and uploads the ISO plus `SHA256SUMS` as an artifact (14 days).

The profiles' `pacman.conf` points `[repo]` at `file:///home/glucy2/Documents/archiso/repo`, so CI mounts the project at that path inside the container.

## Packages

Add a package name to `aur-packages.txt`. To use your own PKGBUILD instead of the AUR one, put it (with any `.install`/patch files) in `packages/<name>/`. Currently `intel-mlc` is custom, to track Intel's download URL and version.

Limitation: only official-repo dependencies are resolved; AUR dependencies of AUR packages are not built.

## Live image defaults

Both profiles share the same defaults (set in each profile's `airootfs/etc/`):

- User `live` (UID 1000, `wheel`), password `live`, passwordless sudo (`sudoers.d/live`).
- Auto-login as `live` on tty1 (`getty@tty1` drop-in); other consoles still prompt for login.
- `root` has an empty password.
- NetworkManager enabled; `systemd-networkd` disabled to avoid conflicts. `NetworkManager-wait-online` is not enabled.
- Hostname equals the profile name (`glucy2-standard` / `glucy2-gpu`) via `/etc/hostname`.

Keep the two profiles' copies in sync when changing these.

## Local build

Requires an Arch host with `base-devel`, `git`, `archiso`, `grub`.

```sh
scripts/build-aur-repo.sh            # writes ./repo
sudo mkarchiso -v -w /tmp/archiso-work -o out glucy2-standard
```

ISOs are written to `out/`. `out/` and `repo/` are git-ignored.
