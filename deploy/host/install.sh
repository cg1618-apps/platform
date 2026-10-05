#!/usr/bin/env bash
# Install the box's own recovery: the hardware watchdog, reboot-on-panic, and
# the Ethernet link watcher. The only part of it that needs root. Read it
# before you run it.
#
#   sudo ~/cg1618/deploy/host/install.sh
#
# RE-RUNNING IS SUPPORTED, and is how a change to anything under deploy/host/
# reaches the box: a deploy brings ~/cg1618 to origin/main but touches nothing
# under /etc or /usr/local. It restarts no container and does not reboot.

set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Hardware watchdog"
install -D -m 644 "${HERE}/etc/cg1618-watchdog-module.conf" /etc/modules-load.d/cg1618-watchdog.conf
install -D -m 644 "${HERE}/etc/cg1618-watchdog.conf" /etc/systemd/system.conf.d/cg1618-watchdog.conf
# A refusal here is the BIOS keeping the watchdog from resetting the board
# ("unable to reset NO_REBOOT flag"). Reported rather than fatal: the rest of
# this script is still worth having without it.
watchdog_ok=1
if ! modprobe iTCO_wdt; then
    watchdog_ok=0
fi
if [ ! -e /dev/watchdog0 ]; then
    watchdog_ok=0
fi
# Re-executing PID 1 is what makes it read system.conf.d. Running services
# are untouched.
systemctl daemon-reexec

echo "==> Reboot on kernel panic"
install -D -m 644 "${HERE}/etc/90-cg1618-panic.conf" /etc/sysctl.d/90-cg1618-panic.conf
sysctl -q -p /etc/sysctl.d/90-cg1618-panic.conf

echo "==> Link watcher"
install -m 755 "${HERE}/netwatch.sh" /usr/local/sbin/cg1618-netwatch
install -m 644 "${HERE}/units/cg1618-netwatch.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable cg1618-netwatch.service
# restart, not start: on a re-run the old script is the one still running.
systemctl restart cg1618-netwatch.service

echo
echo "==> As it stands now, read off the box"
if [ "${watchdog_ok}" -eq 1 ]; then
    wdctl /dev/watchdog0 || true
else
    echo "  WATCHDOG NOT ACTIVE: iTCO_wdt did not load or gave no /dev/watchdog0."
    echo "  Check: journalctl -k | grep -i tco"
fi
echo "  watchdog timeout:       $(systemctl show -p RuntimeWatchdogUSec --value) (systemd feeds it at half that)"
echo "  kernel.panic:           $(sysctl -n kernel.panic)"
echo "  cg1618-netwatch:        $(systemctl is-active cg1618-netwatch.service)"
echo
echo "The watchdog is configured, not proven. Proving it means hanging the box"
echo "on purpose with someone beside it - see docs/shared-stack.md."
