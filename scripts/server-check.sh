#!/usr/bin/env bash
# Read-only survey of the cabin laptop. Changes nothing.
# Asks for your sudo password once (some details need root to read).
#   bash ~/server-check.sh | tee ~/server-check.txt
set -uo pipefail
say()  { printf '\n===== %s =====\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

sudo -v 2>/dev/null || echo "(no sudo: some sections will be partial)"

say "Machine"
echo "Host: $(hostname)   Model: $(cat /sys/class/dmi/id/sys_vendor 2>/dev/null) $(cat /sys/class/dmi/id/product_name 2>/dev/null)"
echo "BIOS: $(cat /sys/class/dmi/id/bios_version 2>/dev/null) ($(cat /sys/class/dmi/id/bios_date 2>/dev/null))"
. /etc/os-release 2>/dev/null && echo "OS: $PRETTY_NAME"
echo "Kernel: $(uname -r)   Up: $(uptime -p)"
echo "CPU: $(nproc) cores, $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
free -h | sed -n '1,3p'
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL 2>/dev/null | grep -v loop
df -hT -x tmpfs -x devtmpfs -x overlay 2>/dev/null

say "Time"
timedatectl 2>/dev/null | sed 's/^ *//'

say "Updates"
echo "Packages with updates waiting (from the last 'apt update'):"
apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null | grep -c '^Inst' || true
echo "Last apt update: $(stat -c %y /var/cache/apt/pkgcache.bin 2>/dev/null | cut -d. -f1)"
echo "Kernel reboot pending: $([ -f /var/run/reboot-required ] && echo yes || echo no)"
dpkg -l unattended-upgrades 2>/dev/null | grep -q '^ii' && echo "unattended-upgrades: installed" || echo "unattended-upgrades: NOT installed"
cat /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null
systemctl is-enabled apt-daily-upgrade.timer 2>/dev/null | sed 's/^/apt-daily-upgrade.timer: /'
grep -hE '^[^/]*Automatic-Reboot' /etc/apt/apt.conf.d/50unattended-upgrades 2>/dev/null

say "Power and battery"
for b in /sys/class/power_supply/*; do
  [ -f "$b/type" ] || continue
  t=$(cat "$b/type")
  case "$t" in
    Battery) echo "$(basename "$b"): $(cat "$b/capacity" 2>/dev/null)% $(cat "$b/status" 2>/dev/null)"
             for pair in "energy_full energy_full_design" "charge_full charge_full_design"; do
               set -- $pair
               [ -f "$b/$1" ] && [ -f "$b/$2" ] && echo "  health: $(( $(cat "$b/$1") * 100 / $(cat "$b/$2") ))% of original capacity"
             done
             for f in charge_control_start_threshold charge_control_end_threshold charge_types charge_type; do
               [ -f "$b/$f" ] && echo "  $f: $(cat "$b/$f")"
             done ;;
    Mains)   echo "AC adapter online: $(cat "$b/online" 2>/dev/null)" ;;
  esac
done
echo "Lid / sleep handling (logind):"
grep -hE '^\s*(HandleLidSwitch|HandleLidSwitchExternalPower|HandleLidSwitchDocked|IdleAction|HandleSuspendKey)' /etc/systemd/logind.conf /etc/systemd/logind.conf.d/*.conf 2>/dev/null || echo "  (defaults: closing the lid SUSPENDS)"
for t in sleep suspend hibernate hybrid-sleep; do echo "  $t.target: $(systemctl is-enabled $t.target 2>/dev/null)"; done
echo "UPower (low-battery shutdown): $(have upower && echo installed || echo NOT installed)"
grep -hE '^(PercentageAction|CriticalPowerAction|UsePercentageForPolicy)' /etc/UPower/UPower.conf 2>/dev/null | sed 's/^/  /'
have cctk && echo "Dell Command Configure (cctk) is installed"
have smbios-token-ctl && echo "libsmbios (smbios-token-ctl) is installed"

say "Network"
ip -br addr | grep -v '^lo'
echo "Default route: $(ip route show default | head -1)"
echo "DNS: $(resolvectl dns 2>/dev/null | awk -F: 'NF>1 && $2!=""{print $2}' | xargs || grep nameserver /etc/resolv.conf | xargs)"
for s in NetworkManager networking systemd-networkd; do systemctl is-active --quiet "$s" 2>/dev/null && echo "Network managed by: $s"; done
have nmcli && nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>/dev/null
ping -c1 -W2 192.168.100.1 >/dev/null 2>&1 && echo "Starlink dish 192.168.100.1: answers" || echo "Starlink dish 192.168.100.1: NO answer"
timeout 3 bash -c '</dev/tcp/192.168.100.1/9200' 2>/dev/null && echo "Starlink port 9200: open" || echo "Starlink port 9200: not reachable"
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && echo "Internet: up" || echo "Internet: DOWN"
have tailscale && { echo "Tailscale:"; tailscale status 2>/dev/null | head -5; }

say "Listening ports"
sudo -n ss -tulpnH 2>/dev/null | awk '{print $1, $5, $7}' | sed 's/users:((//; s/,pid=[0-9]*,fd=[0-9]*//g; s/))//' | sort -u || ss -tulnH | awk '{print $1, $5}' | sort -u

say "Firewall and SSH"
sudo -n ufw status 2>/dev/null | head -3 || echo "ufw: not installed"
echo "nftables chains: $(sudo -n nft list ruleset 2>/dev/null | grep -c chain)"
sudo -n sshd -T 2>/dev/null | grep -E '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication) ' | sed 's/^/sshd: /'
echo "Your SSH keys authorized: $(grep -c . ~/.ssh/authorized_keys 2>/dev/null || echo 0)"
have fail2ban-client && echo "fail2ban: installed" || echo "fail2ban: not installed"

say "Services"
echo "Failed units:"; systemctl --failed --no-legend 2>/dev/null | sed 's/^/  /'
echo "Enabled services:"; systemctl list-unit-files --type=service --state=enabled --no-legend 2>/dev/null | awk '{print "  "$1}'
have nginx && { echo "nginx on the host: $(nginx -v 2>&1) — $(systemctl is-active nginx 2>/dev/null)"; ls /etc/nginx/sites-enabled 2>/dev/null | sed 's/^/  site: /'; }
echo "Journal: $(sudo -n journalctl --disk-usage 2>/dev/null | grep -o '[0-9.]*[KMG]B' || echo unknown); persistent: $([ -d /var/log/journal ] && echo yes || echo no)"

say "Docker"
if have docker; then
  docker --version
  docker compose version 2>/dev/null || echo "docker compose plugin: MISSING"
  echo "Starts at boot: docker $(systemctl is-enabled docker 2>/dev/null), containerd $(systemctl is-enabled containerd 2>/dev/null)"
  id -nG | grep -qw docker && echo "You are in the docker group" || echo "You are NOT in the docker group (docker needs sudo)"
  echo "daemon.json:"; cat /etc/docker/daemon.json 2>/dev/null || echo "  (none — logs grow without limit for containers that don't set it)"
  D="docker"; docker ps >/dev/null 2>&1 || D="sudo -n docker"
  echo; echo "Containers (all):"
  $D ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' 2>/dev/null | while IFS='|' read -r n i s p; do
    r=$($D inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$n" 2>/dev/null)
    proj=$($D inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$n" 2>/dev/null)
    echo "  $n | $i | $s | restart=$r | ${p:-no ports}${proj:+ | compose: $proj}"
  done
  echo; echo "Disk used by Docker:"; $D system df 2>/dev/null
  echo; echo "Volumes:"; $D volume ls --format '  {{.Name}}' 2>/dev/null
else
  echo "Docker: NOT installed"
fi

say "Radio hardware"
lsusb 2>/dev/null | grep -i -E '0bda:2838|rtl' || echo "No RTL-SDR on USB"
lsmod | grep -qE 'dvb_usb_rtl28xxu' && echo "TV-tuner driver LOADED (needs blacklisting)" || echo "TV-tuner driver not loaded"

say "Tempest (listening 70 s on UDP 50222)"
if have python3; then
python3 - <<'PY'
import json, socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("0.0.0.0", 50222))
except OSError as e:
    print("Can't listen on 50222:", e); raise SystemExit
s.settimeout(5)
end, seen = time.time() + 70, {}
while time.time() < end:
    try:
        data, addr = s.recvfrom(4096)
    except socket.timeout:
        continue
    try:
        m = json.loads(data)
    except ValueError:
        continue
    seen[(m.get("serial_number"), m.get("type"))] = addr[0]
for (serial, kind), ip in sorted(seen.items(), key=str):
    print(f"heard {kind} from {serial} at {ip}")
print("Tempest hub is on this network" if seen else "Nothing heard from a Tempest hub")
PY
else
  echo "python3 not installed; skipped"
fi

say "This project"
ls -la /opt/hawksroost 2>/dev/null | head -3 || echo "/opt/hawksroost doesn't exist yet"
ls ~/.ssh/hawksroost_deploy.pub 2>/dev/null && echo "Deploy key already made"
find / -maxdepth 4 -type d -name '.git' -path '*awksroost*' 2>/dev/null | sed 's#/.git$##; s/^/old copy: /'

echo; echo "Done. Nothing was changed."
