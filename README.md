# Oracle Auto Create Shaula

Adaptasi worker Oracle Cloud auto-create buat ngejar slot **Always Free Ampere A1** di OCI, dengan retry loop agresif, backoff yang lebih waras saat kena rate limit, dan notifikasi Telegram.

Repo ini diambil dari kebutuhan real di VPS, terinspirasi dari `Mr0xred/oracle-auto-create`, tapi dirapihin buat workflow operasional yang lebih proper.

## Fitur
- Retry create instance terus sampai tembus
- Fokus ke `VM.Standard.A1.Flex`
- Auto resolve image Ubuntu ARM (`22.04`, fallback `24.04`, fallback ke `OCI_IMAGE_OCID`)
- Telegram notification saat start, fail, dan sukses
- Simpan state lokal biar gak spam notif yang sama terus
- Backoff lebih agresif saat `429 TooManyRequests`
- Tetap fast-poll saat `Out of host capacity`
- Cocok dijalanin sebagai `systemd --user` service

## Struktur Repo
- `oracle_auto_create.py` — worker utama
- `requirements.txt` — dependency Python
- `oracle_auto_create.env.example` — template env
- `oracle-auto-create.service` — unit file systemd user
- `setup.sh` — setup venv, install deps, pasang service
- `install.sh` — install dependency OS dasar

## Requirement
- Python 3.10+
- OCI config aktif di mesin (`~/.oci/config`)
- API key Oracle valid
- systemd user session aktif

Install Python deps manual:

```bash
pip install -r requirements.txt
```

## Quick Start
### 1. Install dependency OS
```bash
bash install.sh
```

### 2. Setup project
```bash
bash setup.sh
```

### 3. Edit env
```bash
cp oracle_auto_create.env.example oracle_auto_create.env
nano oracle_auto_create.env
```

### 4. Start service
```bash
systemctl --user restart oracle-auto-create-adapted.service
systemctl --user status oracle-auto-create-adapted.service
```

## Env minimal
```bash
OCI_AVAILABILITY_DOMAIN=
OCI_DISPLAY_NAME=Shaula
OCI_COMPARTMENT_OCID=
OCI_SUBNET_OCID=
OCI_REGION=ap-batam-1
OCI_SHAPE=VM.Standard.A1.Flex
OCI_IMAGE_OCID=
OCI_IMAGE_OS=Canonical Ubuntu
OCI_IMAGE_OS_VERSION=22.04
OCI_BOOT_VOLUME_SIZE_IN_GB=200
OCI_OCPUS=4
OCI_MEMORY_IN_GBS=24
OCI_SSH_PUBLIC_KEY=
OCI_CONFIG_FILE=/home/ubuntu/.oci/config
OCI_PROFILE=DEFAULT
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
POLL_SECONDS=30
POLL_JITTER_SECONDS=5
```

## Retry Strategy
- `Out of host capacity` / `InternalError`
  - tetap cepat, default `30s + jitter`
- `429 TooManyRequests`
  - backoff eksponensial: `60s -> 120s -> 240s ...` max `1800s`
- error lain
  - backoff eksponensial lebih ringan, max `900s`

Ini lebih cocok buat OCI dibanding nembak kenceng terus sampai rate-limit parah.

## Run manual
```bash
python3 oracle_auto_create.py
```

## Run via systemd user
```bash
mkdir -p ~/.config/systemd/user
cp oracle-auto-create.service ~/.config/systemd/user/oracle-auto-create-adapted.service
systemctl --user daemon-reload
systemctl --user enable --now oracle-auto-create-adapted.service
```

Log:
```bash
journalctl --user -u oracle-auto-create-adapted.service -f
```

## Keamanan
- jangan commit `*.env`
- jangan commit `*.state.json`
- jangan commit private key OCI
- jangan simpan token GitHub di remote URL git

## Asal-usul
Terinspirasi dari:
- https://github.com/Mr0xred/oracle-auto-create

Tapi implementasi repo ini udah disesuaiin buat workflow VPS + Telegram notify + retry tuning untuk OCI.
