#!/usr/bin/env bash
# GCE startup script: driver, Docker, NVIDIA Container Toolkit, repo, venv.
# Runs as root on first boot. Logs to /var/log/syslog.
#
# An alternative is a Deep Learning VM image with drivers preinstalled, which
# removes a class of driver-mismatch problems. Ubuntu 22.04 is used here because
# it is what the plan specifies and what the gate was written against.
set -uo pipefail
exec > >(logger -t agentseism-setup) 2>&1
echo "=== setup start ==="

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential git curl rsync python3-venv python3-pip

echo "=== NVIDIA driver ==="
apt-get install -y -qq ubuntu-drivers-common
ubuntu-drivers install --gpgpu || apt-get install -y -qq nvidia-driver-550-server

echo "=== Docker ==="
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin

echo "=== NVIDIA Container Toolkit ==="
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update -qq
apt-get install -y -qq nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# The login user runs docker without sudo; the gate calls plain `docker run`.
for u in $(ls /home); do usermod -aG docker "$u" 2>/dev/null; done

echo "=== workspace on the persistent disk ==="
# Results live on the boot (persistent) disk. Local SSD, if present, is for the
# model cache only -- it does not survive a stop, and must never hold the only
# copy of a raw result.
mkdir -p /opt/agentseism && chmod 0777 /opt/agentseism
if lsblk -dno NAME,MODEL | grep -qi "nvme.*EphemeralDisk\|nvme_card"; then
  echo "local SSD present -- mount it yourself for HF cache if wanted (not required)"
fi

echo "=== repo at the frozen commit ==="
git clone https://github.com/lyr-ai/agentseism.git /opt/agentseism/repo 2>/dev/null \
  && git -C /opt/agentseism/repo checkout 34ba1fc \
  || echo "clone failed (private repo?) -- clone manually after ssh"

echo "=== verification ==="
uname -m
nvidia-smi || echo "driver not ready -- a reboot is usually needed"
docker run --rm hello-world >/dev/null 2>&1 && echo "docker ok" || echo "docker FAIL"
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1 \
  && echo "docker+gpu ok" || echo "docker+gpu FAIL -- reboot, then retry"

echo "=== setup done ==="
echo "If nvidia-smi failed, reboot and re-run the four verification commands"
echo "in docs/RUNBOOK-c2.md before touching the gate."
