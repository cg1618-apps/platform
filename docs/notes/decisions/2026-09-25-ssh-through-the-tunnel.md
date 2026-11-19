# SSH to the box goes through the tunnel, and is not in the registry

`ssh.cg1618.com` routes to the box's own sshd through the Cloudflare Tunnel
that already exists, behind Access. How it is set up and used is
`docs/shared-stack.md`, "SSH through the tunnel".

**Rejected: an overlay such as Tailscale, or an open port.** The tunnel does
the job with no port opened on either router and nothing new running on the
box. An overlay would add another daemon, another account and another thing
to keep patched, when the platform already has a tunnel with an
authentication gate in front of it.

**Access is the gate, and sshd's key check stands behind it.** Neither is
trusted to be the only one.

**The LAN is the default route and the tunnel the second.** The only client is
the home machine, which is almost always on the box's network. There the LAN
is faster, and it still works when `cloudflared` is what is broken, which is
exactly when the box most needs reaching. Making the tunnel the default buys
one route that works from anywhere, which is worth little with one client that
is nearly always at home. The tunnel is for when the client is away, and for
finding the box after DHCP has moved it.

**The company machine is not a client, on purpose.** It could reach the box
the same way, but that would put the tunnel client, a key for the box and its
hostname on a company-managed machine, and the traffic on the company network.
Work that needs the box is rare enough to wait for the home machine.

**It is emitted by `bin/generate_ingress.py`, like the apex, rather than
listed in `apps.yml`, like `logs`.** `logs` is registered so that
`bin/check-exposure` probes it. SSH has no HTTP service, no port on the
`cg1618` network, no health path and no `<name>-app` alias, so every field the
generator and `bin/deploy` read would be a placeholder or a special case, and
it would appear on the public apex page as an app. Instead the hostname lives
once, as `SSH_HOSTNAME` in the generator, and `bin/check-exposure --all`
imports it and probes it without an entry, so the two cannot drift. The
per-app check a deploy runs does not probe it, because an app's deploy has
nothing to say about SSH.

**sshd stays on the host, not in a container.** It already listens on
`0.0.0.0`, so the tunnel reaches it at `host.docker.internal` with nothing on
the box changed.
