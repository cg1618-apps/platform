# A dead Ethernet link is recovered by a smart plug, not by the box

When `eno1` loses its link and stays down, only removing mains power has ever
brought it back (`docs/shared-stack.md`, "The link that stayed down"). The
recovery is a remotely switchable smart plug on the box's power, cycled from
its app while the box is still running. It is the one option certain to work,
because it is exactly what worked.

Rejected:

- **A scheduled nightly reboot.** A power-button restart did not restore the
  link. A reboot never removes the PHY's power, which stays on standby power
  in every running state, so a schedule would cost a nightly outage and fix
  nothing.
- **Turning AMT off in the BIOS.** AMT is one feature of the management
  engine, which keeps running and keeps its claim on the PHY whether AMT is
  enabled or not; nothing found says disabling it releases the PHY. The
  e1000e driver's only full PHY power-cycle is at probe, and the engine can
  block it.
- **AMT off, Wake-on-LAN off, and `rtcwake -m off`.** With nothing holding the
  PHY on, a power-off with a clock wake-up might power-cycle it the way a plug
  does, with no hardware. Plausible from Intel's datasheets, but it depends on
  HP's firmware cutting PHY power and on an RTC wake from soft-off, neither
  tested. The variant using `S5 Maximum Power Savings` is ruled out, because
  that setting breaks power-on after power loss.
- **A USB Ethernet adapter as a second route.** The only option independent of
  the management engine, and automatic. Not taken: a second cable, a second
  router port and dual-interface routing, for a failure seen once.
- **The `disable-k1` private flag.** Present on this driver and cheap to set,
  but documented for packet loss, not for a lost link.
- **AMT as the out-of-band path.** It talks over the same NIC, so it is
  unreachable in exactly the failure it would be wanted for.
- **The BIOS set to power on after every power loss**, so a box that
  `cg1618-netwatch` had shut down cleanly could be brought back by the plug
  and PostgreSQL would never stop uncleanly. A plug cut on a running box
  already recovers it, and PostgreSQL's crash recovery makes the unclean stop
  cheap, so the BIOS stays untouched and `NETWATCH_POWEROFF_AFTER` stays 0.

**What reopens this:** the link wedging again with the plug in place. The
netwatch diagnostics from that failure are the evidence, and the USB adapter
is the first alternative to revisit, being the only one that removes the
dependency rather than resetting it.
