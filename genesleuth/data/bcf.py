"""bcftools / tabix helper for Windows (feature: run htslib tools through WSL).

bcftools 1.13 and tabix are installed only inside WSL (Ubuntu-22.04). Every slice
that needs them imports `run_bcftools` / `run_tool` from here instead of shelling
out by hand.

Use cases:
    run_bcftools(["view", "-r", "chr2:1-100", url])          -> CompletedProcess (bytes)
    run_bcftools(["view", "-H", to_wsl_path(local_vcf)])      -> local Windows paths converted
    run_tool("tabix", ["-p", "vcf", to_wsl_path(path)])       -> tabix
    run_bcftools(["view"], stdin=vcf_bytes)                   -> data piped on stdin
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

WSL_DISTRO = "Ubuntu-22.04"
# The apt bcftools 1.13 / htslib in Ubuntu 22.04 is built WITHOUT libcurl, so it cannot open https:// URLs
# ("Protocol not supported"). A libcurl-enabled bcftools 1.25 lives in ~/bio/bin (micromamba env); use it
# when present, else fall back to whatever is on PATH.
_LAUNCH = 'P="$HOME/bio/bin"; if [ -x "$P/$0" ]; then export PATH="$P:$PATH"; fi; exec "$0" "$@"'


def to_wsl_path(p) -> str:
    """Convert a Windows path (str or Path) to its /mnt/<drive>/... WSL form.

    URLs and paths that already look POSIX are returned unchanged.
    """
    s = str(p)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", s):
        return s
    if s.startswith("/"):
        return s
    s = s.replace(chr(92), "/")
    if not re.match(r"^[A-Za-z]:/", s):
        s = str(Path(s).resolve()).replace(chr(92), "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    if not m:
        return s
    return "/mnt/" + m.group(1).lower() + "/" + m.group(2)


def run_tool(tool: str, args: list[str], stdin: bytes | None = None,
             timeout: float | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """Run `tool` (bcftools / tabix / bgzip) inside WSL; stdout/stderr come back as bytes."""
    cmd = ["wsl", "-d", WSL_DISTRO, "--exec", "bash", "-c", _LAUNCH, tool, *[str(a) for a in args]]
    return subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout, check=check)


def run_bcftools(args: list[str], stdin: bytes | None = None,
                 timeout: float | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """Run `bcftools <args>` inside WSL. Windows file paths must be passed through to_wsl_path()."""
    return run_tool("bcftools", args, stdin=stdin, timeout=timeout, check=check)


def run_shell(script: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run a bash pipeline inside WSL (for bcftools | bcftools chains). Paths must already be WSL paths."""
    script = 'export PATH="$HOME/bio/bin:$PATH"; ' + script
    cmd = ["wsl", "-d", WSL_DISTRO, "--exec", "bash", "-o", "pipefail", "-c", script]
    return subprocess.run(cmd, capture_output=True, timeout=timeout)
