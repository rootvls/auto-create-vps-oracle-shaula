#!/usr/bin/env python3
"""
Oracle Auto-Create Adapted — relentless instance creation loop
for OCI Always Free Ampere A1 with Telegram notifications.

Inspired by: https://github.com/Mr0xred/oracle-auto-create
"""

import json
import os
import random
import time
import hashlib
from pathlib import Path

import oci
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / "oracle_auto_create.env"
STATE_PATH = BASE_DIR / "oracle_auto_create.state.json"
load_dotenv(ENV_PATH)


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %Z")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def required_env(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def error_signature(exc: Exception) -> str:
    return hashlib.sha256(str(exc).encode("utf-8")).hexdigest()


def telegram_send(message: str) -> None:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] skipped (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()


def notify_dedup(state: dict, channel_key: str, message: str) -> None:
    last = state.setdefault("last_notify", {})
    sig = hashlib.sha256(message.encode("utf-8")).hexdigest()
    if last.get(channel_key) == sig:
        return
    telegram_send(message)
    last[channel_key] = sig
    save_state(state)


def oci_config() -> dict:
    cfg_file = env("OCI_CONFIG_FILE", str(Path.home() / ".oci" / "config"))
    profile = env("OCI_PROFILE", "DEFAULT")
    return oci.config.from_file(file_location=cfg_file, profile_name=profile)


def compute_client() -> oci.core.ComputeClient:
    return oci.core.ComputeClient(oci_config())


def resolve_image_id(compartment_id: str) -> str:
    image_os = env("OCI_IMAGE_OS", "Canonical Ubuntu")
    preferred_versions = [env("OCI_IMAGE_OS_VERSION", "22.04"), "24.04"]
    fallback_image_id = env("OCI_IMAGE_OCID")
    client = compute_client()
    images = client.list_images(
        compartment_id=compartment_id, operating_system=image_os
    ).data

    def pick(version: str):
        candidates = [
            img
            for img in images
            if version in (img.display_name or "")
            and "aarch64" in (img.display_name or "")
        ]
        if not candidates:
            candidates = [
                img for img in images if version in (img.display_name or "")
            ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.time_created or 0, reverse=True)
        return candidates[0]

    last_err = None
    for ver in preferred_versions:
        try:
            chosen = pick(ver)
            if chosen:
                print(f"[{now_ts()}] Resolved image dynamically ({ver}): {chosen.id}")
                return chosen.id
        except Exception as e:
            last_err = e
            continue

    if fallback_image_id:
        print(f"[{now_ts()}] Using fallback image from env: {fallback_image_id}")
        return fallback_image_id

    raise RuntimeError(f"Unable to resolve Ubuntu image OCID; last_err={last_err}")


def build_launch_details() -> oci.core.models.LaunchInstanceDetails:
    display_name = env("OCI_DISPLAY_NAME", "oracle-auto-created")
    compartment_id = required_env("OCI_COMPARTMENT_OCID")
    subnet_id = required_env("OCI_SUBNET_OCID")
    image_id = resolve_image_id(compartment_id)
    ad = required_env("OCI_AVAILABILITY_DOMAIN")
    shape = required_env("OCI_SHAPE")
    boot_volume_size = int(env("OCI_BOOT_VOLUME_SIZE_IN_GB", "200"))
    ocpus = float(env("OCI_OCPUS", "4"))
    mem_gb = float(env("OCI_MEMORY_IN_GBS", "24"))
    ssh_key = env("OCI_SSH_PUBLIC_KEY")

    metadata = {}
    if ssh_key:
        metadata["ssh_authorized_keys"] = ssh_key

    return oci.core.models.LaunchInstanceDetails(
        compartment_id=compartment_id,
        display_name=display_name,
        availability_domain=ad,
        shape=shape,
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=ocpus,
            memory_in_gbs=mem_gb,
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=image_id,
            boot_volume_size_in_gbs=boot_volume_size,
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True,
        ),
        metadata=metadata,
    )


def try_launch(client: oci.core.ComputeClient):
    details = build_launch_details()
    return client.launch_instance(details).data


def launch_message(instance) -> str:
    return (
        f"[{now_ts()}] ✅ Instance created successfully\n"
        f"Name: {instance.display_name}\n"
        f"OCID: {instance.id}\n"
        f"Region: {env('OCI_REGION')}\n"
        f"AD: {env('OCI_AVAILABILITY_DOMAIN')}\n"
        f"Shape: {env('OCI_SHAPE')}"
    )


def failure_message(exc: Exception, attempt: int) -> str:
    return (
        f"[{now_ts()}] ⚠️ Create failed (attempt {attempt})\n"
        f"Reason: {exc}\n"
        f"Region: {env('OCI_REGION')}\n"
        f"AD: {env('OCI_AVAILABILITY_DOMAIN')}\n"
        f"Shape: {env('OCI_SHAPE')}"
    )


def sleep_for_error(exc: Exception, attempt: int) -> int:
    txt = str(exc)
    if "TooManyRequests" in txt or "429" in txt:
        return min(1800, max(60, 60 * (2 ** min(attempt - 1, 5))))
    if "Out of host capacity" in txt or "InternalError" in txt:
        return max(20, int(env("POLL_SECONDS", "30")))
    return min(900, max(30, 30 * (2 ** min(attempt - 1, 4))))


def main():
    client = compute_client()
    state = load_state()
    if state.get("instance_ocid"):
        print(
            f"[{now_ts()}] Instance already created previously: {state['instance_ocid']}"
        )
        return

    poll_seconds = int(env("POLL_SECONDS", "30"))
    jitter_max = int(env("POLL_JITTER_SECONDS", "5"))
    display_name = env("OCI_DISPLAY_NAME", "oracle-auto-created")

    telegram_send(
        f"[{now_ts()}] 🚀 Oracle auto-create started\n"
        f"Name: {display_name}\n"
        f"Region: {env('OCI_REGION')}\n"
        f"Shape: {env('OCI_SHAPE')}\n"
        f"AD: {env('OCI_AVAILABILITY_DOMAIN')}\n"
        f"Interval: {poll_seconds}s (+jitter {jitter_max}s)"
    )

    attempt = int(state.get("attempt", 0))
    while True:
        attempt += 1
        state["attempt"] = attempt
        save_state(state)
        try:
            instance = try_launch(client)
            state["instance_ocid"] = instance.id
            state["created_at"] = now_ts()
            save_state(state)
            msg = launch_message(instance)
            print(msg)
            telegram_send(msg)
            telegram_send(
                f"[{now_ts()}] 🛑 Auto-create stopping after successful create."
            )
            return
        except Exception as exc:
            sig = error_signature(exc)
            state["last_error_sig"] = sig
            state["last_error_text"] = str(exc)
            save_state(state)
            msg = failure_message(exc, attempt)
            print(msg)
            notify_dedup(state, f"err:{sig}", msg)
            sleep_for = sleep_for_error(exc, attempt)
            sleep_for += random.randint(0, max(0, jitter_max))
            print(
                f"[{now_ts()}] Sleeping {sleep_for}s before next attempt..."
            )
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
