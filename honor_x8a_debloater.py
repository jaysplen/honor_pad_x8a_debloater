#!/usr/bin/env python3
"""HONOR Pad X8a reversible ADB debloater.

Standard-library only; no root; package disabling, not system-file deletion.
Every write is opt-in and saved to a local recovery journal.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = "1.2.0"
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "recovery"
SUPPORTED_MODELS = {"NDL-W09", "NDL-L09", "NDL-L03"}
PENDING = {"disabled", "attempted", "unverified"}
RESTORE_COMMANDS = {0: "default-state", 1: "enable", "enabled": "enable"}
JOURNAL_SCHEMA = 1
PACKAGE_RE = re.compile(r"android|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")

@dataclass(frozen=True)
class Target:
    package: str
    name: str
    tier: str  # safe, privacy, optional, review
    impact: str

# Only documented, exact package names are eligible. Absence is expected on many builds.
# SAFE: a small set of standalone apps.
# PRIVACY: third-party preload services in addition to SAFE.
# OPTIONAL: apps the user can choose individually.
# REVIEW: firmware-integrated or setup packages kept for inventory and legacy recovery.
CATALOG = [
    Target("com.hihonor.tips", "HONOR Tips", "safe", "HONOR feature tips disappear."),
    Target("com.hihonor.phoneservice", "My HONOR", "optional", "HONOR support, device checks and offers in the app become unavailable."),
    Target("com.hihonor.gamecenter", "HONOR Game Center", "optional", "HONOR game store and recommendations disappear."),
    Target("com.hihonor.gameassistant", "HONOR Game Assistant", "review", "HONOR gaming enhancements unavailable."),
    Target("com.hihonor.himovie", "HONOR Video", "optional", "HONOR video player unavailable."),
    Target("com.hihonor.music", "HONOR Music", "optional", "HONOR music player unavailable."),
    Target("com.hihonor.videoeditor", "HONOR Video Editor", "optional", "Built-in video editing unavailable."),
    Target("com.hihonor.android.totemweather", "HONOR Weather", "optional", "HONOR weather app/widgets stop."),
    Target("com.hihonor.weather", "HONOR Weather (alternate)", "optional", "HONOR weather app/widgets stop."),
    Target("com.hihonor.magazine", "Magazine Unlock", "review", "Rotating lock-screen pictures stop."),
    Target("com.hihonor.browserhomepage", "HONOR browser content feed", "review", "HONOR browser homepage/news feed may stop."),
    Target("com.hihonor.hnstartupguide", "HONOR startup guide", "review", "Initial onboarding guide unavailable."),
    Target("com.facebook.appmanager", "Meta/Facebook app manager", "privacy", "Background Facebook-app updates via Meta manager stop."),
    Target("com.facebook.services", "Meta/Facebook background services", "privacy", "Meta services integration may be reduced."),
    Target("com.facebook.system", "Meta/Facebook app installer", "privacy", "Preinstalled Meta installer disabled."),
    Target("com.ironsource.appcloud.oobe.huawei", "AppCloud suggestions", "review", "Promotional app recommendations stop."),
    Target("com.netflix.partner.activation", "Netflix preload activation", "optional", "Preload/activation offers may stop; installed Netflix retained."),
    Target("com.hihonor.hiviewtunnel", "HONOR diagnostics uploader", "review", "HONOR diagnostic uploads/feedback may be affected."),
    Target("com.hihonor.android.chr", "HONOR experience/diagnostic service", "review", "OEM diagnostic/experience features may be affected."),
    Target("com.hihonor.bd", "HONOR analytics (legacy package)", "review", "OEM analytics may be affected."),
    Target("com.hihonor.hiview", "HONOR log collector", "review", "Crash analysis and support diagnostics may stop."),
    Target("com.hihonor.autoinstallapkfrommcc", "HONOR regional preload installer", "review", "Automatic regional app installation may stop."),
    Target("com.hihonor.appmarket", "HONOR App Market", "review", "HONOR-store apps may stop receiving updates; Google Play remains."),
    Target("com.hihonor.browser", "HONOR Browser", "optional", "Have another browser installed and set as default first."),
    Target("com.hihonor.notepad", "HONOR Notes", "optional", "Saved notes may become inaccessible: export first."),
    Target("com.hihonor.email", "HONOR Email", "optional", "HONOR email app unavailable; account data in other apps unaffected."),
    Target("com.hihonor.soundrecorder", "HONOR Recorder", "optional", "Recording app unavailable; save recordings first."),
    Target("com.hihonor.lens", "HONOR AI Lens", "optional", "AI image recognition/scanning may stop."),
    Target("com.hihonor.android.clone", "HONOR Device Clone", "optional", "Phone-to-tablet transfer/migration unavailable."),
    Target("com.hihonor.koBackup", "HONOR Backup", "review", "HONOR backup/restore unavailable."),
    Target("com.hihonor.android.thememanager", "HONOR Themes", "review", "Themes or wallpaper controls may stop."),
    Target("com.hihonor.filemanager", "HONOR Files", "optional", "Install a replacement file manager first."),
    Target("com.hihonor.photos", "HONOR Gallery", "optional", "Install another gallery first; camera thumbnails need an opener."),
    Target("com.hihonor.gallery", "HONOR Gallery (alternate)", "optional", "Install another gallery first."),
    Target("com.hihonor.calculator", "HONOR Calculator", "optional", "Install another calculator first."),
    Target("com.hihonor.calendar", "HONOR Calendar", "optional", "Install another calendar first."),
    Target("com.hihonor.search", "HONOR Search", "review", "Launcher and possibly Settings search may stop."),
    Target("com.hihonor.searchservice", "HONOR search service", "review", "Launcher/Settings search may stop; review separately."),
    Target("com.hihonor.assistant", "HONOR assistant cards", "review", "Home suggestions may stop; check launcher afterwards."),
    Target("com.hihonor.android.instantshare", "HONOR Share", "review", "Cross-device file sharing may stop."),
    Target("com.hihonor.airlink", "HONOR AirLink", "review", "HONOR device pairing may stop."),
    Target("com.hihonor.nearby", "HONOR Nearby", "review", "HONOR proximity features may stop."),
    Target("com.hihonor.synergy", "HONOR Synergy", "review", "HONOR cross-device clipboard/features may stop."),
    Target("com.hihonor.handoff", "HONOR Handoff", "review", "HONOR cross-device task continuity may stop."),
    Target("com.hihonor.android.wfdft", "HONOR Wi-Fi Direct transfer", "review", "Wi-Fi Direct transfer features may stop."),
    Target("com.google.android.apps.docs", "Google Drive", "optional", "Drive app and share integration unavailable."),
    Target("com.google.android.apps.tachyon", "Google Meet", "optional", "Meet app unavailable."),
    Target("com.google.android.apps.youtube.music", "YouTube Music", "optional", "YouTube Music app unavailable."),
    Target("com.google.android.videos", "Google TV", "optional", "Google TV app unavailable."),
    Target("com.google.android.gm", "Gmail", "optional", "Gmail app unavailable; other mail clients still work."),
]
TARGETS = {t.package: t for t in CATALOG}
assert len(TARGETS) == len(CATALOG), "Duplicate catalog package"

# Absolute never-touch protections, independent of profile or catalog edits.
PROTECTED = {
    "android",
    "com.hihonor.android.launcher", "com.hihonor.systemmanager", "com.hihonor.android.pushagent",
    "com.hihonor.id", "com.hihonor.hwid", "com.hihonor.hwid.core", "com.hihonor.android.hms",
    "com.hihonor.systemserver", "com.hihonor.powergenie", "com.hihonor.systemappsupdater",
    "com.hihonor.android.thememanager.system", "com.hihonor.contacts", "com.hihonor.phone",
    "com.hihonor.camera", "com.hihonor.deskclock", "com.hihonor.mms", "com.hihonor.hndockbar",
    "com.hihonor.android.FloatTasks", "com.google.android.gms", "com.google.android.gsf",
    "com.google.android.gsf.login", "com.android.vending", "com.android.settings",
    "com.android.systemui", "com.android.providers.settings", "com.android.providers.media",
    "com.google.android.webview", "com.android.webview", "com.android.permissioncontroller",
    "com.google.android.permissioncontroller", "com.android.packageinstaller", "com.google.android.packageinstaller",
    "com.android.inputdevices", "com.android.providers.downloads", "com.android.documentsui",
    "com.android.providers.contacts", "com.android.providers.calendar", "com.android.keychain",
    "com.android.certinstaller", "com.android.bluetooth", "com.android.wifi.resources",
    "com.android.networkstack", "com.google.android.networkstack", "com.android.shell",
    "com.android.externalstorage", "com.android.providers.telephony", "com.android.phone",
    "com.android.nfc", "com.android.location.fused", "com.google.android.ext.services",
    "com.google.android.ext.shared", "com.google.android.configupdater",
    "com.google.android.gms.policy_sidecar_aps", "com.google.android.setupwizard",
    "com.android.backupconfirm", "com.android.sharedstoragebackup", "com.android.providers.userdictionary",
    "com.touchtype.swiftkey", "com.swiftkey.swiftkeyconfigurator", "com.google.android.inputmethod.latin",
    "com.android.inputmethod.latin", "com.baidu.input_huawei", "com.hihonor.android.hwouc",
    "com.hihonor.ouc", "com.hihonor.hwouc", "com.hihonor.lbs", "com.hihonor.trustcircle",
}
PROTECTED_PREFIXES = ("com.android.internal.", "android.", "com.qualcomm.", "com.qti.")
if set(TARGETS) & PROTECTED:
    raise AssertionError("A protected package is present in the catalog")


def protected(pkg: str) -> bool:
    return pkg in PROTECTED or pkg.startswith(PROTECTED_PREFIXES)


def parse_packages(stdout: str) -> set[str]:
    result = set()
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            item = line.removeprefix("package:").strip()
            if PACKAGE_RE.fullmatch(item):
                result.add(item)
    return result


def recognized_device(properties: dict[str, str]) -> bool:
    model = properties.get("ro.product.model", "").strip().upper()
    maker = properties.get("ro.product.manufacturer", "").strip().casefold()
    market = properties.get("ro.product.marketname", "").strip().casefold()
    return (model in SUPPORTED_MODELS and maker == "honor"
            and market in {"", "honor pad x8a", "honor pad x8a wi-fi", "honor pad x8a lte"})


def in_wsl() -> bool:
    return sys.platform == "linux" and (
        "microsoft" in platform.release().casefold() or "WSL_DISTRO_NAME" in os.environ
    )


def windows_adb_candidates() -> list[str]:
    sdk_dirs = [BASE]
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if value := os.environ.get(variable):
            sdk_dirs.append(Path(value))
    if local_appdata := os.environ.get("LOCALAPPDATA"):
        sdk_dirs.append(Path(local_appdata) / "Android" / "Sdk")
    return [str(directory / "platform-tools" / "adb.exe") for directory in sdk_dirs] + ["adb.exe"]


def adb_base(override: str | None = None) -> str:
    wsl = in_wsl()
    if override:
        candidates = [override]
    elif wsl:
        candidates = ["adb.exe", "adb"]
    elif sys.platform == "win32":
        candidates = windows_adb_candidates()
    else:
        candidates = ["adb"]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    if override:
        raise RuntimeError(f"ADB executable not found: {override!r}.")
    if wsl:
        raise RuntimeError("ADB not found. Add Windows Platform-Tools to Windows PATH, then reopen WSL. "
                           "For native WSL 2 USB, install Linux adb and attach the tablet with usbipd.")
    if sys.platform == "linux":
        raise RuntimeError("ADB not found. Install Linux adb and the Android USB rules for your distribution. "
                           "See the Linux USB setup in README.md.")
    if sys.platform == "win32":
        raise RuntimeError("ADB not found. Extract the official Windows platform-tools folder beside this "
                           "script, add it to PATH, or pass --adb with the full path to adb.exe.")
    raise RuntimeError("ADB not found. Install Android SDK Platform-Tools and add adb to PATH.")


def run(args: list[str]) -> str:
    proc = subprocess.run([args[0], "-L", "tcp:5037", *args[1:]], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=35, encoding="utf-8", errors="replace")
    output = (proc.stdout + "\n" + proc.stderr).strip()
    if proc.returncode != 0 or "SecurityException" in output or "Exception occurred" in output:
        raise RuntimeError(f"Command failed ({proc.returncode}): {output[:600]}")
    return proc.stdout.strip()


@dataclass(frozen=True)
class Connection:
    serial: str
    state: str
    transport_id: str
    usb: bool


def connections(listing: str) -> list[Connection]:
    result = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[:2] == ["List", "of"]:
            continue
        state = "no permissions" if parts[1:3] == ["no", "permissions"] else parts[1]
        if state not in {"device", "unauthorized", "offline", "no permissions", "recovery", "sideload", "bootloader"}:
            continue
        transport_id = next((part[13:] for part in parts[2:] if part.startswith("transport_id:")), "")
        result.append(Connection(parts[0], state, transport_id,
                                 any(part.startswith("usb:") for part in parts[2:])))
    return result


@dataclass(frozen=True)
class PackageState:
    setting: int
    system: bool
    restricted: bool


def parse_package_state(output: str, package: str) -> PackageState:
    # An updated app can appear again under "Hidden system packages".
    section = re.search(r"(?ms)^Packages:[ \t]*\n(.*?)(?=^\S|\Z)", output)
    records = re.split(r"(?m)^[ \t]+Package \[([^\n\]]+)\] [^\n]*:$", section[1] if section else "")
    matches = [info for name, info in zip(records[1::2], records[2::2]) if name == package]
    detail = matches[0] if len(matches) == 1 else ""
    owners = re.findall(r"(?m)^\s+User 0:[ \t]+([^\n]*)$", detail)
    uid = re.search(r"(?m)^\s+(?:appId|userId)=(\d+)$", detail)
    flags = set()
    for field in re.findall(r"(?m)^\s+(?:flags|pkgFlags|privateFlags|privatePkgFlags)=\[([^\n\]]*)\]", detail):
        flags.update(field.split())
    if len(owners) == 1 and uid and flags:
        fields = dict(part.split("=", 1) for part in owners[0].split() if "=" in part)
        if (fields.get("installed") == "true" and fields.get("hidden") == "false"
                and fields.get("suspended") == "false" and fields.get("enabled") in {"0", "1", "2", "3", "4"}):
            restricted = (int(uid[1]) < 10000
                          or bool(flags & {"PERSISTENT", "REQUIRED_FOR_SYSTEM_USER", "STATIC_SHARED_LIBRARY"})
                          or bool(re.search(r"(?m)^\s+(?:sharedUser=|overlayTarget=|coreApp=true$|"
                                            r"dynamic libraries:|static library:|SDK library:)", detail)))
            return PackageState(int(fields["enabled"]), "SYSTEM" in flags, restricted)
    raise RuntimeError(f"Could not confirm installed, visible package state for Android user 0: {package}.")


class Device:
    def __init__(self, serial: str | None = None, adb: str | None = None, recovery_dir: Path = DATA_DIR):
        self.adb = adb_base(adb)
        self.recovery_dir = recovery_dir
        listing = self.list_connections()
        matches = [c for c in listing if c.state == "device" and (serial is None or serial == c.serial)]
        if len(matches) != 1:
            states = ", ".join(f"{c.serial} ({c.state})" for c in listing) or "none"
            hint = (" In WSL, use Windows adb.exe with the tablet attached to Windows, or attach it "
                    "to WSL 2 with usbipd and pass --adb adb.") if in_wsl() else ""
            if sys.platform == "linux" and any(c.state == "no permissions" for c in listing):
                hint += " Check the Linux USB permissions setup in README.md."
            if sys.platform == "win32" and not listing:
                hint += " Check the USB data cable and Windows Device Manager. See the Windows 11 setup in README.md."
            raise RuntimeError(f"Expected one authorized tablet using {self.adb}. ADB sees {states}. "
                               "Unlock the tablet and accept the USB debugging prompt. Use --serial "
                               f"to select among multiple devices.{hint}")
        connection = matches[0]
        if not re.fullmatch(r"[1-9][0-9]*", connection.transport_id):
            raise RuntimeError("ADB did not report a transport ID. Update Android SDK Platform-Tools.")
        self.serial = connection.serial
        self.transport_id = connection.transport_id
        self.properties = {key: self.shell("getprop", key) for key in
                           ("ro.product.model", "ro.product.marketname", "ro.product.name",
                            "ro.build.version.release", "ro.build.version.sdk", "ro.product.manufacturer",
                            "ro.build.fingerprint")}
        self.device_key = hashlib.sha256(self.serial.encode()).hexdigest()[:16]

    def list_connections(self) -> list[Connection]:
        return connections(run([self.adb, "devices", "-l"]))

    def shell(self, *parts: str) -> str:
        return run([self.adb, "-t", self.transport_id, "shell", *parts])

    def packages(self, *switches: str, package: str | None = None) -> set[str]:
        scope = [package] if package else []
        return parse_packages(self.shell("pm", "list", "packages", *switches, "--user", "0", *scope))

    def inventory(self) -> dict:
        installed = self.packages()
        enabled = self.packages("-e")
        disabled = self.packages("-d")
        system = self.packages("-s")
        if (not enabled or not system or installed != enabled | disabled
                or enabled & disabled or not system <= installed):
            raise RuntimeError("Package inventory was incomplete or changed during the scan. Run scan again.")
        return {"installed": installed, "enabled": enabled, "disabled": disabled, "system": system}

    def require_supported(self) -> None:
        if not recognized_device(self.properties):
            raise RuntimeError("Device identity did not match a supported HONOR Pad X8a "
                               "(NDL-W09 / NDL-L09 / NDL-L03). Use 'scan' to check the reported properties.")

    def require_writable(self) -> None:
        self.require_supported()
        if self.serial.casefold() == "unknown":
            raise RuntimeError("ADB did not report a USB serial. Recovery requires a stable tablet serial.")
        matches = [c for c in self.list_connections() if c.serial == self.serial
                   and c.transport_id == self.transport_id and c.state == "device"]
        if not matches:
            raise RuntimeError("The tablet connection changed. Reconnect by USB and rerun the command.")
        if not matches[0].usb:
            # Some ADB USB backends omit the usb: descriptor.
            try:
                usb_serial = run([self.adb, "-d", "get-serialno"])
            except RuntimeError as exc:
                raise RuntimeError("Could not verify the USB connection. Connect only the tablet by USB.") from exc
            if usb_serial != self.serial:
                raise RuntimeError("Changes require the selected tablet to be connected by USB.")
        if self.shell("am", "get-current-user") != "0":
            raise RuntimeError("Switch the tablet to its owner (Android user 0) before making changes.")

    def package_state(self, package: str) -> PackageState:
        return parse_package_state(self.shell("dumpsys", "package", package), package)


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def filename_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


@contextmanager
def mutation_lock(device: Device):
    directory = device.recovery_dir
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{device.device_key}.lock").open("a+b") as lock:
        try:
            if sys.platform == "win32":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"Could not lock recovery data in {directory}: {exc}") from exc
        yield


def to_json_inventory(inv: dict) -> dict:
    return {k: sorted(v) for k, v in inv.items()}


def take_scan(device: Device) -> tuple[dict, dict, Path]:
    inv = device.inventory()
    review = sorted(inv["installed"] & TARGETS.keys())
    untouched_vendor = sorted(p for p in inv["enabled"] if
                              (p.startswith(("com.hihonor.", "com.huawei.", "com.facebook."))) and p not in TARGETS)
    path = device.recovery_dir / f"scan_{filename_stamp()}.json"
    payload = {
        "version": VERSION,
        "created_utc": iso_now(),
        "device": device.properties,
        "device_key": device.device_key,
        "recognized_x8a": recognized_device(device.properties),
        "inventory": to_json_inventory(inv),
        "catalog_matches": [{"package": p, "tier": TARGETS[p].tier,
                             "name": TARGETS[p].name, "impact": TARGETS[p].impact,
                             "system_app": p in inv["system"], "enabled": p in inv["enabled"]} for p in review],
        "unreviewed_vendor_packages": untouched_vendor,
    }
    write_json(path, payload)
    return inv, payload, path


def selection(inv: dict, profile: str, selected: list[str] | None = None) -> tuple[list[Target], list[str]]:
    if selected is not None:
        choices = []
        bad = []
        for pkg in selected:
            if pkg not in TARGETS or protected(pkg):
                bad.append(f"{pkg} (not explicitly approved in catalog)")
            elif TARGETS[pkg].tier == "review":
                bad.append(f"{pkg} (inventory only due to firmware or setup integration)")
            elif pkg not in inv["installed"]:
                bad.append(f"{pkg} (not installed)")
            elif pkg not in inv["system"]:
                bad.append(f"{pkg} (not marked as a system package; leave user-installed apps alone)")
            elif pkg in inv["disabled"]:
                bad.append(f"{pkg} (already disabled)")
            elif pkg not in inv["enabled"]:
                bad.append(f"{pkg} (not confirmed enabled)")
            else:
                choices.append(TARGETS[pkg])
        return sorted(set(choices), key=lambda t: (t.tier, t.name)), bad
    allowed = {"safe": {"safe"}, "privacy": {"safe", "privacy"}}[profile]
    choices = [t for t in CATALOG if t.tier in allowed and t.package in inv["installed"] & inv["enabled"]
               and t.package in inv["system"] and t.package not in inv["disabled"] and not protected(t.package)]
    return sorted(choices, key=lambda t: (t.tier, t.name)), []


def show_selection(items: list[Target], bad: list[str]) -> None:
    print(f"\nPlanned changes: {len(items)} system app(s)\n")
    for i, t in enumerate(items, 1):
        print(f" {i:>2}. [{t.tier.upper():7s}] {t.name:<32s} {t.package}")
        print(f"      Effect: {t.impact}")
    if bad:
        print("\nNot eligible (no action):")
        for p in bad:
            print(" -", p)
    print("\nMethod: pm disable-user --user 0 changes the app setting for the tablet owner.")


def can_disable(state: PackageState) -> bool:
    return state.system and not state.restricted and state.setting in {0, 1}


def do_apply(device: Device, items: list[Target], source: str) -> bool:
    device.require_writable()
    if not items:
        print("Nothing new to disable for this selection.")
        return True
    if any(TARGETS.get(t.package) != t or protected(t.package) or t.tier == "review" for t in items):
        raise RuntimeError("Selection contains a package outside the disable allowlist.")
    print("\nMagicOS dependencies vary by firmware. Keep the recovery journal and test affected features.")
    phrase = f"DISABLE {len(items)}"
    if input(f"\nType {phrase} to apply: ").strip() != phrase:
        print("Cancelled. No changes made.")
        return True
    with mutation_lock(device):
        return apply_confirmed(device, items, source)


def apply_confirmed(device: Device, items: list[Target], source: str) -> bool:
    device.require_writable()
    pending = {entry["package"] for _, _, entry in pending_entries(device, last=False)}
    if pending & {t.package for t in items}:
        raise RuntimeError("A selected package has an unresolved journal. Run restore before applying again.")
    inv = device.inventory()
    changes = []
    for t in items:
        pkg = t.package
        state = device.package_state(pkg)
        if pkg not in inv["enabled"] & inv["system"] or not can_disable(state):
            raise RuntimeError(f"Package state changed or is restricted: {pkg}. No changes made.")
        changes.append({"package": pkg, "name": t.name, "tier": t.tier, "before": state.setting,
                        "status": "queued", "impact": t.impact})
    journal = device.recovery_dir / f"transaction_{filename_stamp()}.json"
    record = {"version": VERSION, "schema": JOURNAL_SCHEMA, "created_utc": iso_now(), "device": device.properties,
              "device_key": device.device_key, "source": source, "user": 0,
              "method": "pm disable-user --user 0", "status": "running", "changes": changes}
    write_json(journal, record)
    print(f"\nRecovery journal: {journal}")
    for entry in changes:
        pkg = entry["package"]
        try:
            device.require_writable()
            state = device.package_state(pkg)
            if (state.setting != entry["before"] or not can_disable(state)
                    or pkg not in device.packages("-e", package=pkg)):
                raise RuntimeError("Package state changed after confirmation.")
            entry["status"] = "attempted"
            write_json(journal, record)
            device.shell("pm", "disable-user", "--user", "0", pkg)
            state = device.package_state(pkg)
            if state.setting != 3 or not state.system or pkg not in device.packages("-d", package=pkg):
                raise RuntimeError("Could not verify disabled-user state.")
            entry["status"] = "disabled"
            print(f"[OK] {pkg}")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            if entry["status"] == "attempted":
                entry["status"] = "unverified"
            entry["error"] = str(exc)[:400]
            print(f"[STOP] {pkg}: {exc}")
        write_json(journal, record)
        if entry["status"] != "disabled":
            break
    success = sum(e["status"] == "disabled" for e in changes)
    record["status"] = "complete" if success == len(items) else "partial"
    write_json(journal, record)
    print(f"\nDisabled: {success}/{len(items)}. Journal: {journal.name}")
    if success or any(e["status"] == "unverified" for e in changes):
        print("If anything breaks or a change is unverified, run 'restore'.")
    return success == len(items)


def pending_entries(device: Device, last: bool) -> list[tuple[Path, dict, dict]]:
    pending = []
    for path in sorted(device.recovery_dir.glob("transaction_*.json"), reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Unreadable recovery journal {path}: {exc}") from exc
        if not isinstance(record, dict) or not isinstance(record.get("device_key"), str):
            raise RuntimeError(f"Invalid recovery journal: {path}")
        if record["device_key"] != device.device_key:
            continue
        legacy = record.get("version") == "1.0.0"
        if (record.get("method") != "pm disable-user --user 0"
                or not (legacy or (record.get("schema") == JOURNAL_SCHEMA and record.get("user") == 0))
                or not isinstance(record.get("changes"), list)):
            raise RuntimeError(f"Invalid recovery journal: {path}")
        entries = []
        seen = set()
        for entry in record["changes"]:
            if not isinstance(entry, dict):
                raise RuntimeError(f"Invalid change in recovery journal: {path}")
            pkg, status, before = entry.get("package"), entry.get("status"), entry.get("before")
            valid_before = before == "enabled" if legacy else type(before) is int and before in {0, 1}
            if (not isinstance(pkg, str) or pkg not in TARGETS or protected(pkg) or pkg in seen
                    or not isinstance(status, str) or status not in PENDING | {"queued", "missing", "restored", "unchanged"}
                    or not valid_before):
                raise RuntimeError(f"Invalid or ineligible change in recovery journal: {path}")
            seen.add(pkg)
            if status in PENDING:
                entries.append((path, record, entry))
        pending.extend(reversed(entries))
        if last and pending:
            break
    return pending


def restore_entry(device: Device, entry: dict) -> None:
    pkg, before = entry["package"], entry["before"]
    device.require_writable()
    if pkg not in device.packages(package=pkg):
        if pkg in device.inventory()["installed"]:
            raise RuntimeError("Package inventory changed during recovery. Reconnect and retry restore.")
        entry["status"] = "missing"
        print("[SKIP] No longer installed for Android user 0:", pkg)
        return
    state = device.package_state(pkg)
    if not state.system:
        raise RuntimeError("The package is no longer a system app.")
    if state.setting != 3:
        original = state.setting == before or (before == "enabled" and state.setting in {0, 1})
        if original and pkg in device.packages("-e", package=pkg):
            entry["status"] = "restored"
            print("[OK] Already enabled:", pkg)
        else:
            entry["status"] = "unchanged"
            print("[SKIP] Tablet no longer has the disabled-user setting recorded by this tool:", pkg)
        return
    command = RESTORE_COMMANDS[before]
    device.shell("pm", command, "--user", "0", pkg)
    expected = 0 if command == "default-state" else 1
    if device.package_state(pkg).setting != expected or pkg not in device.packages("-e", package=pkg):
        raise RuntimeError("Could not verify the restored enabled setting.")
    entry["status"] = "restored"
    print("[OK] Restored:", pkg)


def restore(device: Device, last: bool) -> bool:
    device.require_writable()
    with mutation_lock(device):
        summary = pending_entries(device, last)
        if not summary:
            print("No changes from this tool need recovery on this tablet.")
            return True
        print("\nRestore plan:")
        for _, _, entry in summary:
            before = entry["before"]
            setting = "Android default" if before == 0 else "explicitly enabled"
            if before == "enabled":
                setting += " (legacy journal)"
            print(f" - {entry['package']} ({setting})")
        phrase = f"RESTORE {len(summary)}"
        if input(f"\nType {phrase} to restore: ").strip() != phrase:
            print("Cancelled.")
            return True
        for path, record, entry in summary:
            try:
                restore_entry(device, entry)
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f"[STOP] {entry['package']}: {exc}")
                entry["restore_error"] = str(exc)[:400]
                write_json(path, record)
                return False
            entry.pop("restore_error", None)
            write_json(path, record)
        print("\nRecovery pass complete. Check affected features.")
        return True


def scan_and_print(device: Device) -> None:
    inv, payload, path = take_scan(device)
    print("\nHONOR Pad X8a debloater - inventory only")
    print("Model:", device.properties.get("ro.product.model"), "| Android:", device.properties.get("ro.build.version.release"))
    print("Recognized device:", payload["recognized_x8a"])
    print("Installed:", len(inv["installed"]), "| System:", len(inv["system"]), "| Disabled:", len(inv["disabled"]))
    print("Catalog matches:", len(payload["catalog_matches"]), "| Unreviewed vendor packages:", len(payload["unreviewed_vendor_packages"]))
    print("\nCatalog matches (system apps marked *, review entries are inventory only):")
    for item in payload["catalog_matches"]:
        state = "enabled" if item["enabled"] else "disabled"
        print(f" {('*' if item['system_app'] else ' ')} [{item['tier']}, {state}] {item['package']}")
    print("\nUnreviewed vendor packages (NEVER disabled automatically):")
    for pkg in payload["unreviewed_vendor_packages"]:
        print("  ", pkg, "[PROTECTED]" if protected(pkg) else "")
    print("\nFull local inventory:", path)
    print("Contains installed package names and device build metadata. Review before sharing.")


def cmd_plan(device: Device, profile: str, selected: list[str] | None = None) -> tuple[list[Target], list[str]]:
    device.require_supported()
    inv, _, path = take_scan(device)
    items, bad = selection(inv, profile, selected)
    eligible = []
    for item in items:
        if can_disable(device.package_state(item.package)):
            eligible.append(item)
        else:
            bad.append(f"{item.package} (protected by live package state or flags)")
    print(f"Device: {device.properties['ro.product.model']} | Inventory snapshot: {path.name}")
    show_selection(eligible, bad)
    return eligible, bad


def show_optional(device: Device) -> None:
    device.require_supported()
    inv = device.inventory()
    for item in CATALOG:
        if item.tier == "optional" and item.package in inv["installed"]:
            state = "system app" if item.package in inv["system"] else "user app (ineligible)"
            print(f" - {item.name}: {item.package} [{state}]\n   {item.impact}")
    print("To opt in, run 'select PACKAGE' with the exact package ID.")


def menu(device: Device) -> None:
    print(f"\nHONOR Pad X8a Debloater v{VERSION}")
    print("Detected:", device.properties.get("ro.product.model"), "| Android", device.properties.get("ro.build.version.release"))
    print("ADB:", device.adb)
    while True:
        print("\n 1  Scan tablet / save inventory (read-only)")
        print(" 2  Preview conservative cleanup (read-only)")
        print(" 3  APPLY conservative cleanup (confirmation required)")
        print(" 4  Preview privacy cleanup (read-only)")
        print(" 5  APPLY privacy cleanup (confirmation required)")
        print(" 6  Show optional packages for manual selection")
        print(" 7  Restore last operation")
        print(" 8  Restore all changes made by this tool")
        print(" 0  Exit")
        choice = input("Select: ").strip()
        try:
            if choice == "0":
                return
            elif choice == "1":
                scan_and_print(device)
            elif choice in {"2", "3", "4", "5"}:
                profile = "safe" if choice in {"2", "3"} else "privacy"
                items, _ = cmd_plan(device, profile)
                if choice in {"3", "5"}:
                    do_apply(device, items, profile)
            elif choice == "6":
                show_optional(device)
            elif choice == "7":
                restore(device, last=True)
            elif choice == "8":
                restore(device, last=False)
            else:
                print("Unknown selection.")
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            print("ERROR:", exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reversible, opt-in HONOR Pad X8a debloater (USB ADB, no root).")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--serial", help="ADB device serial; required if multiple authorized Android devices are connected.")
    parser.add_argument("--adb", metavar="EXECUTABLE", help="ADB executable or path (WSL prefers adb.exe by default).")
    parser.add_argument("--recovery-dir", type=Path, metavar="DIRECTORY", default=DATA_DIR,
                        help="Inventory and journal directory (default: recovery beside the script).")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("scan", help="Read-only device scan and full local JSON package inventory.")
    plan = sub.add_parser("plan", help="Preview exact changes without modifying tablet.")
    plan.add_argument("--profile", choices=["safe", "privacy"], default="safe")
    apply = sub.add_parser("apply", help="Disable approved system apps (interactive confirmation).")
    apply.add_argument("--profile", choices=["safe", "privacy"], default="safe")
    sub.add_parser("optional", help="List optional known features/apps, without making changes.")
    select = sub.add_parser("select", help="Disable ONLY named catalogued apps, with confirmation.")
    select.add_argument("packages", nargs="+", help="Exact package IDs from the catalog; no wildcards.")
    restore_parser = sub.add_parser("restore", help="Restore enabled settings recorded by this tool.")
    scope = restore_parser.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true", help="Restore all recorded operations.")
    scope.add_argument("--last", action="store_true", help="Restore the last unrestored operation (default).")
    args = parser.parse_args(argv)
    try:
        device = Device(args.serial, args.adb, args.recovery_dir.expanduser().resolve())
        if args.cmd == "scan":
            scan_and_print(device)
        elif args.cmd == "plan":
            cmd_plan(device, args.profile)
        elif args.cmd == "apply":
            items, _ = cmd_plan(device, args.profile)
            return 0 if do_apply(device, items, args.profile) else 1
        elif args.cmd == "optional":
            show_optional(device)
        elif args.cmd == "select":
            if len(args.packages) != len(set(args.packages)):
                raise RuntimeError("Duplicate package in selection; fix the command.")
            items, bad = cmd_plan(device, "safe", args.packages)
            if bad:
                print("Some requested packages are not eligible; for safety, nothing will be changed.")
                return 2
            return 0 if do_apply(device, items, "manual") else 1
        elif args.cmd == "restore":
            return 0 if restore(device, last=not args.all) else 1
        else:
            menu(device)
    except KeyboardInterrupt:
        print("\nInterrupted. Run restore if any changes were made.")
        return 130
    except EOFError:
        print("\nInput ended. Run interactively to confirm changes.", file=sys.stderr)
        return 1
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
