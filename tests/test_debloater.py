"""Offline safety tests, no tablet or adb required."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import honor_x8a_debloater as d

class DebloatTests(unittest.TestCase):
    def test_catalog_has_no_protected_components(self):
        self.assertTrue(all(not d.protected(p) for p in d.TARGETS))
        self.assertEqual(len(d.TARGETS), len(d.CATALOG))

    def test_recognizes_only_intended_models(self):
        props = {"ro.product.manufacturer": "HONOR", "ro.product.marketname": "HONOR Pad X8a"}
        for model in ("NDL-W09", "NDL-L09", "NDL-L03"):
            self.assertTrue(d.recognized_device({**props, "ro.product.model": model}))
        for model in ("NDL2-L09", "HEY-W09", "Pixel 9", "HONOR Pad X8a clone"):
            self.assertFalse(d.recognized_device({**props, "ro.product.model": model}))
        props["ro.product.model"] = "NDL-W09"
        self.assertFalse(d.recognized_device({**props, "ro.product.marketname": "HONOR Pad X9"}))
        self.assertFalse(d.recognized_device({**props, "ro.product.manufacturer": ""}))

    def test_parse_package_output_without_command_injection(self):
        result = d.parse_packages("package:com.hihonor.tips\npackage:com.hihonor.tips;rm -rf /\n"
                                  "hello\npackage:com.android.vending\npackage:android\n")
        self.assertEqual(result, {"com.hihonor.tips", "com.android.vending", "android"})

    def test_safe_does_not_include_privacy_or_optional(self):
        installed = set(d.TARGETS)
        inv = {"installed": installed, "enabled": installed, "disabled": set(), "system": installed}
        choices, bad = d.selection(inv, "safe")
        self.assertFalse(bad)
        self.assertTrue(choices)
        self.assertEqual({c.package for c in choices}, {"com.hihonor.tips"})

    def test_privacy_excludes_optional(self):
        installed = set(d.TARGETS)
        inv = {"installed": installed, "enabled": installed, "disabled": set(), "system": installed}
        choices, _ = d.selection(inv, "privacy")
        privacy = {c.package for c in choices if c.tier == "privacy"}
        self.assertEqual(privacy, {"com.facebook.appmanager", "com.facebook.services", "com.facebook.system"})
        self.assertTrue(all(c.tier in {"safe", "privacy"} for c in choices))
        self.assertFalse(d.selection(inv, "safe", ["com.hihonor.appmarket"])[0])

    def test_selection_only_system_apps(self):
        pkg = "com.hihonor.tips"
        inv = {"installed": {pkg}, "enabled": {pkg}, "disabled": set(), "system": set()}
        self.assertEqual(d.selection(inv, "safe")[0], [])
        self.assertEqual(d.selection(inv, "safe", [pkg])[0], [])
        self.assertTrue(d.selection(inv, "safe", [pkg])[1])

    def test_protected_never_selectable(self):
        pkg = "com.hihonor.android.launcher"
        inv = {"installed": {pkg}, "enabled": {pkg}, "disabled": set(), "system": {pkg}}
        self.assertFalse(d.selection(inv, "safe", [pkg])[0])
        self.assertTrue(d.selection(inv, "safe", [pkg])[1])

    def test_no_previously_disabled_package_selected(self):
        pkg = "com.hihonor.tips"
        inv = {"installed": {pkg}, "enabled": set(), "disabled": {pkg}, "system": {pkg}}
        self.assertEqual(d.selection(inv, "safe")[0], [])
        self.assertEqual(d.selection(inv, "safe", [pkg])[0], [])

    def test_complete_wsl_adb_preference_and_override(self):
        with patch.object(d, "in_wsl", return_value=True), patch.object(d.shutil, "which", side_effect={
            "adb.exe": "/mnt/c/Platform Tools/adb.exe", "adb": "/usr/bin/adb",
        }.get):
            self.assertEqual(d.adb_base(), "/mnt/c/Platform Tools/adb.exe")
            self.assertEqual(d.adb_base("adb"), "/usr/bin/adb")
            with self.assertRaisesRegex(RuntimeError, "executable not found"):
                d.adb_base("missing")
        with patch.object(d, "in_wsl", return_value=True), patch.object(d.shutil, "which", side_effect={
            "adb": "/usr/bin/adb",
        }.get):
            self.assertEqual(d.adb_base(), "/usr/bin/adb")

    def test_native_linux_uses_adb(self):
        with patch.object(d.sys, "platform", "linux"), patch.object(d, "in_wsl", return_value=False), \
                patch.object(d.shutil, "which", return_value="/usr/bin/adb") as which:
            self.assertEqual(d.adb_base(), "/usr/bin/adb")
            which.assert_called_once_with("adb")

    def test_windows_prefers_local_platform_tools_and_honors_override(self):
        local_adb = str(d.BASE / "platform-tools" / "adb.exe")
        executables = {local_adb: local_adb, "adb.exe": "PATH adb", "override.exe": "override adb"}
        with patch.object(d.sys, "platform", "win32"), patch.object(d.shutil, "which", side_effect=executables.get):
            self.assertEqual(d.adb_base(), local_adb)
            self.assertEqual(d.adb_base("override.exe"), "override adb")

    def test_windows_finds_android_sdk_without_path(self):
        sdk_dir = Path("Android SDK")
        sdk_adb = str(sdk_dir / "platform-tools" / "adb.exe")
        standard_adb = str(Path("Local AppData") / "Android" / "Sdk" / "platform-tools" / "adb.exe")
        locations = {"ANDROID_HOME": str(sdk_dir), "LOCALAPPDATA": "Local AppData"}
        with patch.dict(d.os.environ, locations, clear=True), patch.object(d.sys, "platform", "win32"), \
                patch.object(d.shutil, "which", side_effect={sdk_adb: sdk_adb, standard_adb: standard_adb}.get):
            self.assertEqual(d.adb_base(), sdk_adb)
            del d.os.environ["ANDROID_HOME"]
            self.assertEqual(d.adb_base(), standard_adb)

    def test_linux_usb_permission_error_points_to_setup(self):
        listing = "List of devices attached\nX8A no permissions (udev rules missing); usb:1-2 transport_id:5\n"
        with patch.object(d.sys, "platform", "linux"), patch.object(d, "in_wsl", return_value=False), \
                patch.object(d, "adb_base", return_value="/usr/bin/adb"), patch.object(d, "run", return_value=listing) as run:
            with self.assertRaisesRegex(RuntimeError, r"no permissions.*Linux USB permissions"):
                d.Device()
            run.assert_called_once_with(["/usr/bin/adb", "devices", "-l"])

    def test_usb_transport_pin_survives_multiple_authorized_devices(self):
        listing = ("List of devices attached\n"
                   "tablet device usb:1-2 product:NDL transport_id:12\n"
                   "other unauthorized usb:1-3 transport_id:3\n"
                   "127.0.0.1:5555 device transport_id:4\n")
        with patch.object(d, "adb_base", return_value="adb"), patch.object(d, "run") as run:
            props = {"ro.product.model": "NDL-W09", "ro.product.manufacturer": "HONOR"}
            def output(args):
                if args[1:] == ["devices", "-l"]:
                    return listing
                self.assertEqual(args[1:4], ["-t", "12", "shell"])
                return "0" if args[4:6] == ["am", "get-current-user"] else props.get(args[-1], "")
            run.side_effect = output
            device = d.Device("tablet")
            device.require_writable()
            listing = listing.replace("transport_id:12", "transport_id:13")
            with self.assertRaisesRegex(RuntimeError, "connection changed"):
                device.require_writable()

    def test_usb_proof_required_even_without_usb_descriptor(self):
        listing = "List of devices attached\ntablet device transport_id:12\n"
        with patch.object(d, "adb_base", return_value="adb"), patch.object(d, "run") as run:
            result = {"devices": listing, "ro.product.model": "NDL-W09", "ro.product.manufacturer": "HONOR",
                      "get-serialno": "other", "get-current-user": "0"}
            run.side_effect = lambda args: result.get(args[1] if args[1] == "devices" else args[-1], "")
            device = d.Device()
            with self.assertRaisesRegex(RuntimeError, "connected by USB"):
                device.require_writable()
            result["get-serialno"] = "tablet"
            device.require_writable()
            result["get-current-user"] = "10"
            with self.assertRaisesRegex(RuntimeError, "Android user 0"):
                device.require_writable()

    def test_package_dump_uses_live_package_for_owner(self):
        dump = """Activity Resolver Table:
  test
Packages:
  Package [com.hihonor.tips] (abc123):
    appId=10234
    flags=[ SYSTEM HAS_CODE ]
    User 0: installed=true hidden=false suspended=false enabled=3 instant=false
    User 10: installed=true hidden=false suspended=false enabled=1 instant=false

Hidden system packages:
  Package [com.hihonor.tips] (def456):
    appId=10234
    pkgFlags=[ SYSTEM HAS_CODE ]
    User 0: installed=true hidden=false suspended=false enabled=0 instant=false
"""
        self.assertEqual(d.parse_package_state(dump, "com.hihonor.tips"), d.PackageState(3, True, False))
        restricted = dump.replace("SYSTEM HAS_CODE", "SYSTEM PERSISTENT").replace("enabled=3", "enabled=0")
        self.assertFalse(d.can_disable(d.parse_package_state(restricted, "com.hihonor.tips")))
        with self.assertRaisesRegex(RuntimeError, "confirm installed"):
            d.parse_package_state(dump.replace("enabled=3", "enabled=9"), "com.hihonor.tips")

if __name__ == "__main__":
    unittest.main()
