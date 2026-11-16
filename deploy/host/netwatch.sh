#!/usr/bin/env bash
# cg1618-netwatch: notice the box's Ethernet link staying down, record the
# NIC's state while it is down, and try to bring it back without a human.
#
# Why it exists: on 2026-10-05 at 18:35 eno1 lost carrier with nothing logged
# before it, and never regained it. The host stayed healthy for half an hour,
# a power-button restart did NOT bring the link back, and only pulling the
# power cable did. The I219-LM is Intel AMT's port and stays on standby power
# while the box is plugged in, so a reboot does not reset it. A link that drops
# and returns within seconds - as on 2026-10-03, three seconds - is left alone.
#
# What it does, measured from when the link was first seen down:
#   STEP_AFTER[0]  save diagnostics, then bounce the interface (ip link down/up)
#   STEP_AFTER[1]  unbind and rebind the network driver
#   STEP_AFTER[2]  remove the PCI device and rescan the bus
#   POWEROFF_AFTER power off cleanly - OFF unless configured, see below
#
# EXPECT THE RESETS NOT TO WORK. On 2026-10-05 a full boot, which re-initialises
# the driver and the device more thoroughly than all three, left the link down.
# They are cheap and run against a link that is already dead; the diagnostics
# are the part that is guaranteed to be useful, because nothing was recorded
# about the NIC the first time.
#
# Poweroff is OFF (NETWATCH_POWEROFF_AFTER=0) and stays off on this box. Its
# BIOS restores the previous power state, so a box that powered itself off
# stays off even when the smart plug cycles mains power; the plug recovers a
# dead link only by cutting a box that is still running. See
# docs/shared-stack.md, "The box recovers itself".
#
# A link with no address is down too. On 2026-11-16 eno1 dropped at 19:21:59
# and had carrier again 85 seconds later, so the watcher logged "link back" and
# stood down - but the DHCP lease had gone with the link, and no new one came
# until 20:04. Forty-one minutes with carrier and no IPv4 address is a box with
# no route out, and the tunnel failed the whole time. So once the link is up,
# the watcher also wants a global IPv4 address on it, measured from when the
# address was first seen missing:
#   ADDR_STEP_AFTER[0]  save diagnostics, then ask networkd for a fresh lease
#   ADDR_STEP_AFTER[1]  reconfigure the interface from scratch
#   every ADDR_RENEW_EVERY after that, ask for a fresh lease again
# networkd's own DHCP client keeps retrying with a growing backoff; these steps
# restart it from the beginning rather than wait out the interval. They cannot
# make a router answer that is not answering - on 2026-11-16 the server at
# 192.168.100.1 took 11 to 41 minutes per boot - so, as with the link, the
# diagnostics are the part guaranteed to be useful.

set -euo pipefail

IFACE="${NETWATCH_IFACE:-eno1}"
SYS="${NETWATCH_SYS:-/sys}"
INTERVAL="${NETWATCH_INTERVAL:-30}"
LOG_DIR="${NETWATCH_LOG_DIR:-/var/log/cg1618-netwatch}"
POWEROFF_AFTER="${NETWATCH_POWEROFF_AFTER:-0}"
STEP_AFTER=(180 360 600)
ADDR_STEP_AFTER=(60 180)
ADDR_RENEW_EVERY=300

log() { echo "netwatch: $*"; }

# 1 when the link is up, 0 otherwise. Reading `carrier` fails outright while
# the interface is administratively down or absent - mid-rebind, mid-rescan -
# and either of those is "no link" for this purpose.
carrier() {
    local value
    value="$(cat "${SYS}/class/net/${IFACE}/carrier" 2>/dev/null)" || value=0
    if [ "${value}" = "1" ]; then echo 1; else echo 0; fi
}

# The step that is due, or nothing. $1 is how long the link has been down, in
# seconds; $2 how many reset steps have already run; $3 POWEROFF_AFTER.
# Pure, so the escalation is tested without touching a NIC.
step_due() {
    local down_for="$1" done_steps="$2" poweroff_after="$3"
    local names=(bounce rebind rescan)
    if [ "${done_steps}" -lt "${#STEP_AFTER[@]}" ] \
        && [ "${down_for}" -ge "${STEP_AFTER[${done_steps}]}" ]; then
        echo "${names[${done_steps}]}"
        return
    fi
    if [ "${poweroff_after}" -gt 0 ] && [ "${down_for}" -ge "${poweroff_after}" ]; then
        echo poweroff
    fi
}

# 1 when the interface holds a global IPv4 address, 0 otherwise. Link-local
# and IPv6 do not count: neither gets the tunnel out.
has_ipv4() {
    if [ -n "$(ip -4 -o addr show dev "${IFACE}" scope global 2>/dev/null)" ]; then
        echo 1
    else
        echo 0
    fi
}

# The address step that is due, or nothing. $1 is how long the link has had
# carrier and no address, in seconds; $2 how many address steps have run.
# Pure, like step_due. Unlike the link steps these never run out: after the
# named ones, a renew falls due every ADDR_RENEW_EVERY seconds.
addr_step_due() {
    local missing_for="$1" done_steps="$2"
    local names=(renew reconfigure)
    local count="${#ADDR_STEP_AFTER[@]}"
    if [ "${done_steps}" -lt "${count}" ]; then
        if [ "${missing_for}" -ge "${ADDR_STEP_AFTER[${done_steps}]}" ]; then
            echo "${names[${done_steps}]}"
        fi
        return
    fi
    local last="${ADDR_STEP_AFTER[$((count - 1))]}"
    if [ "${missing_for}" -ge $((last + (done_steps - count + 1) * ADDR_RENEW_EVERY)) ]; then
        echo renew
    fi
}

# Everything worth knowing about the NIC while the link is down. Each command
# is allowed to fail: a missing tool must not cost the rest of the record.
diagnose() {
    local pci="$1" file
    mkdir -p "${LOG_DIR}"
    file="${LOG_DIR}/$(date +%Y%m%dT%H%M%S).txt"
    {
        echo "== $(date -Is) ${IFACE} (${pci}) link down"
        echo "== ip -d link"; ip -d link show "${IFACE}" 2>&1
        echo "== ethtool"; ethtool "${IFACE}" 2>&1
        echo "== ethtool --show-eee"; ethtool --show-eee "${IFACE}" 2>&1
        echo "== ethtool -S"; ethtool -S "${IFACE}" 2>&1
        echo "== lspci -vvv"; lspci -vvv -s "${pci}" 2>&1
        echo "== kernel log"; journalctl -k -n 80 --no-pager 2>&1
    } >"${file}" || true
    log "diagnostics saved to ${file}"
}

# What the interface and networkd's DHCP client looked like while the link
# had carrier and no address.
diagnose_addr() {
    local file
    mkdir -p "${LOG_DIR}"
    file="${LOG_DIR}/$(date +%Y%m%dT%H%M%S)-no-address.txt"
    {
        echo "== $(date -Is) ${IFACE} has carrier and no IPv4 address"
        echo "== ip addr"; ip addr show "${IFACE}" 2>&1
        echo "== ip route"; ip route 2>&1
        echo "== ip neigh"; ip neigh show dev "${IFACE}" 2>&1
        echo "== networkctl status"; networkctl status "${IFACE}" --no-pager 2>&1
        echo "== systemd-networkd log"; journalctl -u systemd-networkd -n 80 --no-pager 2>&1
    } >"${file}" || true
    log "diagnostics saved to ${file}"
}

run_step() {
    local step="$1" pci="$2" driver="$3"
    case "${step}" in
        bounce)
            ip link set "${IFACE}" down || true
            sleep 2
            ip link set "${IFACE}" up || true
            ;;
        rebind)
            echo "${pci}" >"${SYS}/bus/pci/drivers/${driver}/unbind" || true
            sleep 2
            echo "${pci}" >"${SYS}/bus/pci/drivers/${driver}/bind" || true
            ;;
        rescan)
            echo 1 >"${SYS}/bus/pci/devices/${pci}/remove" || true
            sleep 2
            echo 1 >"${SYS}/bus/pci/rescan" || true
            ;;
        poweroff)
            systemctl poweroff
            ;;
        renew)
            networkctl renew "${IFACE}" || true
            ;;
        reconfigure)
            networkctl reconfigure "${IFACE}" || true
            ;;
    esac
}

main() {
    # Resolved once, at start: after an unbind or a remove the interface is
    # gone from /sys/class/net, and with it the only path to these two names.
    local pci driver
    pci="$(basename "$(readlink -f "${SYS}/class/net/${IFACE}/device")")"
    driver="$(basename "$(readlink -f "${SYS}/class/net/${IFACE}/device/driver")")"
    log "watching ${IFACE} (${pci}, ${driver}); steps at ${STEP_AFTER[*]}s, poweroff after ${POWEROFF_AFTER}s (0 = never); with no address, steps at ${ADDR_STEP_AFTER[*]}s then a renew every ${ADDR_RENEW_EVERY}s"

    local down_since=0 done_steps=0 last_step=none now step
    local addr_since=0 addr_steps=0 addr_last=none
    while true; do
        now="$(date +%s)"
        if [ "$(carrier)" = "1" ]; then
            if [ "${down_since}" -ne 0 ]; then
                log "${IFACE} link back after $((now - down_since))s; last step run: ${last_step}"
            fi
            down_since=0 done_steps=0 last_step=none
            if [ "$(has_ipv4)" = "1" ]; then
                if [ "${addr_since}" -ne 0 ]; then
                    log "${IFACE} address back after $((now - addr_since))s; last step run: ${addr_last}"
                fi
                addr_since=0 addr_steps=0 addr_last=none
            else
                if [ "${addr_since}" -eq 0 ]; then
                    addr_since="${now}"
                    log "${IFACE} has carrier and no IPv4 address"
                fi
                step="$(addr_step_due "$((now - addr_since))" "${addr_steps}")"
                if [ -n "${step}" ]; then
                    [ "${addr_steps}" -eq 0 ] && diagnose_addr
                    log "${IFACE} without an address $((now - addr_since))s: running ${step}"
                    run_step "${step}" "${pci}" "${driver}"
                    addr_last="${step}"
                    addr_steps=$((addr_steps + 1))
                fi
            fi
        else
            # A dead link is the link steps' case; the address clock restarts
            # when carrier returns, so the lease gets its normal chance first.
            addr_since=0 addr_steps=0 addr_last=none
            if [ "${down_since}" -eq 0 ]; then
                down_since="${now}"
                log "${IFACE} link down"
            fi
            step="$(step_due "$((now - down_since))" "${done_steps}" "${POWEROFF_AFTER}")"
            if [ -n "${step}" ]; then
                [ "${done_steps}" -eq 0 ] && diagnose "${pci}"
                log "${IFACE} down $((now - down_since))s: running ${step}"
                run_step "${step}" "${pci}" "${driver}"
                last_step="${step}"
                [ "${step}" = poweroff ] || done_steps=$((done_steps + 1))
            fi
        fi
        sleep "${INTERVAL}"
    done
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main
fi
