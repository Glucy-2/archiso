#!/usr/bin/env python3
"""Boot an ISO in QEMU and verify it works end to end (CI smoke test).

Usage: scripts/test-iso.py ISO [--log FILE]

The kernel, initramfs and kernel command line are taken from the ISO itself
(boot/grub/grub.cfg), booted directly with `-kernel` so the serial console can
be enabled. Checks:
  * initramfs sets up the zram-backed cowspace and mounts it
  * the system reaches the serial login prompt
  * login as live/live works and the motd (fastfetch) is printed
  * root is an overlay and /run/archiso/cowspace is ext4 on /dev/zram0

Requires: qemu-system-x86_64, bsdtar (libarchive), python3-pexpect.
Defaults: guest RAM = host MemAvailable (total - used) minus 1 GiB (min 2 GiB),
guest CPUs = host CPUs. Overrides: ISO_TEST_MEMORY (QEMU size, e.g. 4G),
ISO_TEST_CPUS, ISO_TEST_BOOT_TIMEOUT (seconds).
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

import pexpect

RESERVED_MIB = 1024
MIN_MEMORY_MIB = 2048
INSTALL_DIR = "arch"
ARCH = "x86_64"
FAIL_PATTERNS = [
    "Falling back to interactive prompt",
    "Kernel panic",
]


def default_memory():
    """Host total - used (= MemAvailable) - 1 GiB, as a QEMU size in MiB."""
    with open("/proc/meminfo") as f:
        avail_kib = next(int(l.split()[1]) for l in f if l.startswith("MemAvailable:"))
    return f"{max(avail_kib // 1024 - RESERVED_MIB, MIN_MEMORY_MIB)}M"


def extract_boot_files(iso, dest):
    kernel = f"{INSTALL_DIR}/boot/{ARCH}/vmlinuz-linux"
    initrd = f"{INSTALL_DIR}/boot/{ARCH}/initramfs-linux.img"
    grub_cfg = "boot/grub/grub.cfg"
    subprocess.run(["bsdtar", "-xf", iso, "-C", dest, kernel, initrd, grub_cfg], check=True)
    return os.path.join(dest, kernel), os.path.join(dest, initrd), os.path.join(dest, grub_cfg)


def kernel_cmdline(grub_cfg):
    """Kernel arguments of the first `linux .../vmlinuz-linux` entry."""
    with open(grub_cfg) as f:
        for line in f:
            m = re.match(r"\s*linux\s+\S*vmlinuz-linux\s+(.*?)\s*$", line)
            if m:
                return m.group(1)
    raise SystemExit(f"no vmlinuz-linux entry in {grub_cfg}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso")
    ap.add_argument("--log", default="serial.log")
    args = ap.parse_args()

    kvm = os.access("/dev/kvm", os.R_OK | os.W_OK)
    boot_timeout = int(os.environ.get("ISO_TEST_BOOT_TIMEOUT", 300 if kvm else 1500))
    memory = os.environ.get("ISO_TEST_MEMORY") or default_memory()
    cpus = os.environ.get("ISO_TEST_CPUS") or str(len(os.sched_getaffinity(0)))
    print(f"kvm={'yes' if kvm else 'no (tcg, slow)'} memory={memory} cpus={cpus} boot_timeout={boot_timeout}s", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        kernel, initrd, grub_cfg = extract_boot_files(args.iso, tmp)
        cmdline = kernel_cmdline(grub_cfg)
        if "cow_device=/dev/zram0" not in cmdline:
            raise SystemExit(f"boot entry lacks cow_device=/dev/zram0: {cmdline}")
        cmdline += " console=ttyS0,115200"
        print(f"cmdline: {cmdline}", flush=True)

        qemu = [
            "qemu-system-x86_64",
            "-machine", "q35" + (",accel=kvm" if kvm else ",accel=tcg"),
            "-cpu", "host" if kvm else "max",
            "-m", memory, "-smp", cpus,
            "-display", "none", "-serial", "stdio", "-monitor", "none",
            "-no-reboot",
            "-nic", "user",
            "-drive", f"file={args.iso},media=cdrom,readonly=on",
            "-kernel", kernel, "-initrd", initrd, "-append", cmdline,
        ]
        child = pexpect.spawn(qemu[0], qemu[1:], encoding="utf-8", timeout=boot_timeout)
        log = open(args.log, "w")
        child.logfile_read = log

        def wait(pattern, timeout=boot_timeout):
            idx = child.expect([pattern] + FAIL_PATTERNS + [pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
            if idx == 0:
                return
            reason = (FAIL_PATTERNS + ["QEMU exited", "timeout"])[idx - 1]
            raise RuntimeError(f"waiting for {pattern!r}: {reason}")

        def shell(command, pattern, timeout=60):
            # Readline enables bracketed paste when it starts reading a line. Typing
            # earlier is lost: fastfetch in the motd drains the tty while probing it.
            wait(re.escape("\x1b[?2004h"), timeout)
            child.sendline(command)
            wait(pattern, timeout)

        try:
            wait(r"Formatting /dev/zram0")
            wait(r"Device '/dev/zram0' mounted successfully")
            wait(r"login: ")
            child.sendline("live")
            wait(r"Password: ", 60)
            child.sendline("live")
            wait(r"Kernel:", 120)  # fastfetch output from /etc/profile.d/motd.sh
            shell(
                'echo "ZRAM_COW=$(findmnt -no SOURCE,FSTYPE /run/archiso/cowspace)'
                ' ROOT=$(findmnt -no FSTYPE /)"',
                r"ZRAM_COW=/dev/zram0 ext4 ROOT=overlay",
            )
            shell('echo "ZRAM_COMP=$(cat /sys/block/zram0/comp_algorithm)"', r"ZRAM_COMP=[^$\r\n]+")
            print(child.after.strip(), flush=True)
            # Informational only: failed units are reported, not treated as test failures.
            shell(
                "systemctl --failed --no-legend --plain | sed 's/^/FAILED_UNIT: /'; echo UNITS_DONE_$((6*7))",
                r"UNITS_DONE_42",
            )
            for unit in re.findall(r"FAILED_UNIT: \S+\.\w+", child.before):
                print(unit, flush=True)
            # live is not root and a serial login is not an active seat: polkit would refuse plain poweroff.
            wait(re.escape("\x1b[?2004h"), 60)
            child.sendline("sudo poweroff")
            child.expect(pexpect.EOF, timeout=180)
        except RuntimeError as e:
            log.flush()
            print(f"FAIL: {e}", file=sys.stderr)
            with open(args.log) as f:
                print("---- last serial output ----", file=sys.stderr)
                print("".join(f.readlines()[-80:]), file=sys.stderr)
            child.terminate(force=True)
            return 1
        finally:
            log.close()

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
