#!/bin/sh
# One-shot, pinned SSH master for the operator's existing R candidate GPU.
# Run in a visible local terminal; enter the password there, never in chat.
set -eu

: "${R4_KNOWN_HOSTS:?set an owner-private pinned known_hosts path}"
: "${R4_SOCKET_DIR:?set an owner-private socket directory}"
: "${R4_APPROVED_HOST:?set the approved instance host}"
: "${R4_APPROVED_PORT:?set the approved SSH port}"
: "${R4_APPROVED_USER:?set the approved SSH user}"
r4_known_hosts=$R4_KNOWN_HOSTS
r4_socket_dir=$R4_SOCKET_DIR
r4_expected_fingerprint=SHA256:uenZe8XSigDXekroROhjmIi41k60yqNOYTjqt0mf7XM

[ -d "$r4_socket_dir" ] || { echo "Missing private socket directory" >&2; exit 2; }
r4_actual_fingerprint=$(ssh-keygen -lf "$r4_known_hosts" | awk '{print $2}')
[ "$r4_actual_fingerprint" = "$r4_expected_fingerprint" ] || {
  echo "Pinned host fingerprint changed; refusing connection" >&2
  exit 2
}
exec ssh -M -N -T -S "$r4_socket_dir/control" \
  -o StrictHostKeyChecking=yes \
  -o HostKeyAlgorithms=ssh-ed25519 \
  -o UserKnownHostsFile="$r4_known_hosts" \
  -o GlobalKnownHostsFile=/dev/null \
  -o NumberOfPasswordPrompts=1 \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=2 \
  -p "$R4_APPROVED_PORT" "$R4_APPROVED_USER@$R4_APPROVED_HOST"
