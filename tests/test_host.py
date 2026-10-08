"""deploy/host: the box's own recovery - watchdog, panic reboot, link watcher.

None of it can run here: it needs the box's NIC and root. What is checked is
the escalation logic of netwatch.sh, which is a pure function, and the
promises install.sh makes about what it will not touch.
"""

import os
import subprocess
from pathlib import Path

import pytest
from test_deploy import usable_bash

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "deploy" / "host"
NETWATCH = HOST / "netwatch.sh"
INSTALL = HOST / "install.sh"
UNIT = HOST / "units" / "cg1618-netwatch.service"


def bash_call(snippet: str, env: dict[str, str] | None = None) -> str:
    exe = usable_bash()
    if exe is None:
        pytest.skip("no working bash on this machine")
    script = f'source "{NETWATCH.as_posix()}"; {snippet}'
    out = subprocess.run([exe, "-c", script], capture_output=True, text=True, check=True, env=env)
    return out.stdout.strip()


def step_due(down_for: int, done: int, poweroff_after: int = 0) -> str:
    return bash_call(f"step_due {down_for} {done} {poweroff_after}")


# --- escalation -------------------------------------------------------------


def test_a_brief_drop_is_left_alone():
    # 2026-10-03: down three seconds, back on its own. Bouncing the interface
    # in that window would turn a blip into a real outage.
    assert step_due(3, 0) == ""
    assert step_due(179, 0) == ""


def test_the_steps_run_in_order_and_once_each():
    assert step_due(180, 0) == "bounce"
    assert step_due(200, 1) == ""
    assert step_due(360, 1) == "rebind"
    assert step_due(600, 2) == "rescan"
    # All three spent and poweroff off: nothing more, however long it stays down.
    assert step_due(86400, 3) == ""


def test_poweroff_is_off_by_default_and_follows_its_setting():
    # The refusal needs the clock past any plausible threshold, or "nothing"
    # would be the answer because nothing was due yet.
    assert step_due(86400, 3, 0) == ""
    # The mirror case, same clock: configured, it fires.
    assert step_due(86400, 3, 1800) == "poweroff"
    assert step_due(1799, 3, 1800) == ""


def test_poweroff_waits_for_the_resets_before_it():
    # A threshold shorter than the last reset must not skip the resets.
    assert step_due(600, 2, 300) == "rescan"


def test_the_default_poweroff_is_zero():
    assert 'POWEROFF_AFTER="${NETWATCH_POWEROFF_AFTER:-0}"' in NETWATCH.read_text(encoding="utf-8")


# --- reading the link -------------------------------------------------------


@pytest.mark.parametrize(("content", "expected"), [("1\n", "1"), ("0\n", "0"), (None, "0")])
def test_carrier(tmp_path, content, expected):
    # None: the file is unreadable, which is what /sys gives for an interface
    # that is down or mid-rebind. That is "no link", not an error.
    net = tmp_path / "class" / "net" / "eno1"
    net.mkdir(parents=True)
    if content is not None:
        (net / "carrier").write_text(content)
    env = {**os.environ, "NETWATCH_SYS": tmp_path.as_posix()}
    assert bash_call("carrier", env) == expected


# --- what install.sh and the unit promise -------------------------------------


def code(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_install_never_reboots_or_bounces_containers():
    body = code(INSTALL)
    for forbidden in ("reboot", "docker", "systemctl restart docker", "poweroff"):
        assert forbidden not in body, forbidden


def test_root_runs_a_copy_not_the_checkout():
    # The service runs as root; executing a file in a user-writable checkout
    # would hand that user root.
    assert "ExecStart=/usr/local/sbin/cg1618-netwatch" in UNIT.read_text(encoding="utf-8")
    assert "/usr/local/sbin/cg1618-netwatch" in code(INSTALL)


def test_the_watcher_does_not_wait_for_the_network():
    # It exists for the case where the network never comes online.
    assert "network-online.target" not in code(UNIT)


WATCHDOG_UNIT = HOST / "units" / "cg1618-watchdog-module.service"


def test_the_watchdog_driver_is_not_left_to_modules_load():
    # systemd-modules-load honours Ubuntu's blacklist of iTCO_wdt, so an entry
    # there loads nothing; the box booted on 2026-10-08 with no /dev/watchdog0.
    # The one mention left is the line removing what earlier versions installed.
    mentions = [line for line in code(INSTALL).splitlines() if "modules-load.d" in line]
    assert mentions == ["rm -f /etc/modules-load.d/cg1618-watchdog.conf"]


def test_the_watchdog_driver_loads_early_at_every_boot():
    unit = code(WATCHDOG_UNIT)
    assert "ExecStart=/usr/sbin/modprobe iTCO_wdt" in unit
    # Before sysinit.target, so PID 1 finds /dev/watchdog0 while it still looks.
    assert "DefaultDependencies=no" in unit
    assert "Before=sysinit.target" in unit
    assert "WantedBy=sysinit.target" in unit
    assert "systemctl enable cg1618-watchdog-module.service" in code(INSTALL)


PANIC_CONF = HOST / "etc" / "90-cg1618-panic.conf"


def test_lockups_panic_so_the_box_reboots():
    # The TCO watchdog cannot reset this board, so a lockup has to become a
    # panic for kdump or kernel.panic to recover it.
    conf = code(PANIC_CONF)
    assert "kernel.panic = 10" in conf
    assert "kernel.softlockup_panic = 1" in conf
    assert "kernel.hardlockup_panic = 1" in conf
