#!/usr/bin/env bash
# Provision the C2 host on GCE. Checks quota first, because a new project
# ships 0 GPU quota and that blocks harder than anything else here.
#
# Nothing in this script touches the experiment. It creates a machine.
set -uo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
ZONE="${ZONE:-us-central1-a}"
NAME="${NAME:-agentseism-c2}"
MACHINE="a2-ultragpu-1g"          # 1 x A100 80GB, 12 vCPU, 170 GB RAM
DISK_GB="${DISK_GB:-200}"          # persistent SSD; results live HERE, not on local SSD

[ -n "$PROJECT" ] || { echo "set PROJECT or run: gcloud config set project <id>"; exit 1; }
echo "project $PROJECT   zone $ZONE   name $NAME"

echo
echo "──── quota: the usual blocker ────"
# A new project has NVIDIA_A100_80GB_GPUS = 0. Raising it is a request with a
# turnaround, so it is checked before anything is created.
REGION="${ZONE%-*}"
gcloud compute regions describe "$REGION" --project "$PROJECT" \
  --format="table[box](quotas.metric,quotas.limit,quotas.usage)" 2>/dev/null \
  | grep -Ei "A2_CPUS|A100_80GB|^METRIC|─" || echo "  (could not read quotas)"
echo
echo "Need: A2_CPUS >= 12 and NVIDIA_A100_80GB_GPUS >= 1 in $REGION."
echo "If either is 0, request an increase before continuing; nothing below will work."
read -rp "Quota confirmed? [y/N] " ok
[ "$ok" = "y" ] || { echo "stopping"; exit 1; }

echo
echo "──── create ────"
# --maintenance-policy=TERMINATE is required for GPUs, and is also what we want:
#   a maintenance event must fail the experiment visibly rather than silently
#   resume it. --no-restart-on-failure for the same reason -- results from an
#   auto-restarted run must never be mixed into the original batch.
# A2 machine types carry their GPU and local SSD by machine type; no
# --accelerator flag. Verify local SSD after boot with lsblk.
gcloud compute instances create "$NAME" \
  --project "$PROJECT" --zone "$ZONE" \
  --machine-type "$MACHINE" \
  --provisioning-model=STANDARD \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size="${DISK_GB}GB" --boot-disk-type=pd-ssd \
  --maintenance-policy=TERMINATE --no-restart-on-failure \
  --metadata-from-file=startup-script=inference/vm_setup.sh \
  --scopes=cloud-platform \
  --tags=agentseism-c2 || exit 1

echo
echo "──── network: SSH only ────"
echo "No ingress rule is created for port 8000. vLLM binds 127.0.0.1 and is"
echo "reached over localhost only -- that is the entire point of colocation."
echo "If you need to look at it from here, use a tunnel, not a firewall rule:"
echo "  gcloud compute ssh $NAME --zone $ZONE -- -L 8000:127.0.0.1:8000"

cat <<EOF

──── next ────
  gcloud compute ssh $NAME --zone $ZONE
  tail -f /var/log/syslog            # startup script progress

When it reports ready, follow docs/RUNBOOK-c2.md from §1.

When the batch is downloaded and verified:
  gcloud compute instances delete $NAME --zone $ZONE
An A100 80GB bills while it exists, including while it sits idle after the run.
EOF
