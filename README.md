# HONOR Pad X8a Debloater

A Python tool that inventories a USB-connected HONOR Pad X8a and optionally disables selected preinstalled apps for the tablet owner (Android user 0). It uses Android's package manager to change an app's enabled setting. The system image, bootloader and app data stay in place. Every tablet change requires a typed confirmation and a local recovery journal.

For a first run, download and extract the source ZIP from [GitHub Releases](https://github.com/jaysplen/honor_pad_x8a_debloater/releases), then follow the setup for [WSL](#run-from-wsl-over-usb), [Linux Mint, Ubuntu or Debian](#boot-linux-mint-22-from-usb), or [Windows and macOS](#native-windows-and-macos). Python 3.9+ and ADB are the only runtime requirements.

**Status.** The tests simulate ADB and package states. Real Pad X8a hardware and regional MagicOS builds still need field validation. Start with the read-only scan and preview.

## Run from WSL over USB

On each PC, install Python 3.9+ **inside WSL** and download [Android SDK Platform-Tools for Windows](https://developer.android.com/tools/releases/platform-tools). Extract the full folder and add it to your **Windows user PATH**. Open a new WSL session after updating PATH. WSL can run Windows executables directly, so Windows handles the physical USB connection. [Microsoft's WSL interoperability guide](https://learn.microsoft.com/en-us/windows/wsl/interop#run-windows-tools-from-linux)

1. On the tablet, tap **Build number** seven times under **Settings > About tablet**. The label can vary by MagicOS build. Enable **USB debugging** in Developer options.
2. Connect the unlocked tablet with a USB data cable. In WSL, run `adb.exe devices -l`. Accept the computer's RSA fingerprint on the tablet and repeat the command until the tablet is listed as `device`.
3. From the project directory in WSL, run:

   ```sh
   ./start_macos_linux.sh scan
   ./start_macos_linux.sh plan --profile safe
   ./start_macos_linux.sh
   ```

   The last command opens the menu. To launch from a copy that lost the executable bit, use `sh start_macos_linux.sh` with the same arguments.

WSL prefers `adb.exe` when it is on PATH. You can also pass its full WSL path, including quotes if the path contains spaces:

```sh
./start_macos_linux.sh --adb "/mnt/c/Android/platform-tools/adb.exe" scan
```

If ADB shows **unauthorized**, unlock the tablet and accept the prompt. If the list is empty, check the cable and try `adb.exe devices -l` in PowerShell as well. If PowerShell also sees no ADB device, check Windows Device Manager and the [official OEM USB driver guidance](https://developer.android.com/studio/run/oem-usb). If PowerShell sees the tablet but WSL cannot find the executable, use the full path above and check WSL interoperability.

### Native ADB in WSL 2

Use this path if you want WSL to own the USB connection. Install Linux ADB and follow Microsoft's guide to install `usbipd-win`. Run `usbipd list` in PowerShell to find the tablet's bus ID. Run `usbipd bind --busid BUSID` in an elevated PowerShell window once, then `usbipd attach --wsl --busid BUSID` with a WSL session open. Windows releases access to the device while it is attached to WSL. Linux ADB may require the distribution's Android USB permission rules. [Microsoft's WSL USB guide](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)

```sh
adb devices -l
./start_macos_linux.sh --adb adb scan
```

Authorize the Linux ADB key on the tablet if prompted. To return the tablet to Windows, unplug it or run `usbipd detach --busid BUSID` in PowerShell.

## Boot Linux Mint 22 from USB

Use the same launcher after booting Mint. Linux talks directly to the tablet over USB. Mint 22 uses the Ubuntu 24.04 package base, and the commands below also work on Ubuntu 24.04 and Debian 12. [Linux Mint 22 release notes](https://www.linuxmint.com/rel_wilma_cinnamon.php)

```sh
sudo apt update
sudo apt install python3 adb android-sdk-platform-tools-common
```

On Debian 13, use `sudo apt install python3 adb android-udev-rules` after `sudo apt update`. [Ubuntu USB rules](https://packages.ubuntu.com/noble/android-sdk-platform-tools-common), [Debian 12 ADB](https://packages.debian.org/bookworm/adb), [Debian 13 USB rules](https://packages.debian.org/trixie/android-udev-rules)

Enable **USB debugging** in Developer options on the tablet. Connect it with a USB data cable, unlock it, and accept the RSA authorization prompt for Linux. From the project directory, run these commands as your normal user:

```sh
adb devices -l
sh start_macos_linux.sh scan
sh start_macos_linux.sh plan --profile safe
```

Start the scan once ADB lists the tablet as `device`. Run `sh start_macos_linux.sh` for the menu. Invoking the script with `sh` also works when the copy of the launcher lacks an executable bit.

**Keep the recovery journal on storage that survives a reboot.** If Mint is fully installed on the stick, the default `recovery/` folder beside the script works when the project is on that installation. In a nonpersistent live session, mount a writable partition or another drive and use the same `--recovery-dir` for scan, apply, and restore. Replace the example path with your mounted directory. [Linux Mint live-session guide](https://linuxmint-installation-guide.readthedocs.io/en/latest/install.html#the-live-session)

```sh
sh start_macos_linux.sh --recovery-dir "/media/your-user/your-drive/x8a-recovery" scan
```

### Linux USB permissions

If you just installed the USB rules, unplug and reconnect the tablet. If ADB reports `unauthorized`, unlock the tablet and accept its prompt. If it reports `no permissions`, check `id -nG`. If the error mentions `plugdev` and the group is missing from your session, run `sudo usermod -aG plugdev "$(id -un)"`, sign out and back in, and reconnect. Run ADB and the launcher as your normal desktop user. [Android Developers USB setup](https://developer.android.com/studio/run/device#setting-up)

If the packaged rules still miss the tablet, use `lsusb` with USB debugging enabled and identify the tablet's `VID:PID` by comparing the list with the cable unplugged. Install `usbutils` if you need `lsusb`. Run `sudoedit /etc/udev/rules.d/70-honor-x8a-adb.rules` and add the line below, replacing `vvvv` and `pppp` with the actual four-digit hexadecimal IDs. This grants USB access for the matching device IDs to the active local desktop user.

```text
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="vvvv", ATTR{idProduct}=="pppp", TAG+="uaccess"
```

Run `sudo udevadm control --reload-rules`, unplug and reconnect the tablet, then retry `adb devices -l`. If the tablet is absent even from `lsusb`, try a different USB data cable or port.

### Native Windows and macOS

On Windows, install Python 3.9+ and Windows Platform-Tools, then double-click `Start_Windows.bat` or run `py -3 honor_x8a_debloater.py`. On macOS, install Python 3.9+ and macOS Platform-Tools and run `./start_macos_linux.sh`. ADB must list an authorized device before you launch the tool. The script uses only the Python standard library.

## What can change on the tablet

The write path requires a live USB connection to an exact supported model code with an HONOR manufacturer property. A reported marketing name must agree with Pad X8a. Supported identifiers are **NDL-W09** (Wi-Fi) and **NDL-L09 / NDL-L03** (LTE). Other identities can run `scan`. The scan records the current Android version and firmware fingerprint so you can identify the build being reviewed.

| Selection | Scope | Expected effect |
| --- | --- | --- |
| Conservative (`safe`) | HONOR Tips (`com.hihonor.tips`), if it passes the live checks | Removes access to HONOR's feature tips |
| Privacy (`privacy`) | The conservative selection plus eligible Meta/Facebook preload manager, installer and background services | Can affect Meta app preload, update and integration behavior |
| Manual (`select`) | Exact catalogued app IDs, such as My HONOR or HONOR Notes | The affected app or feature becomes unavailable. Export notes or other app data first if you rely on it. |
| Inventory only (`review`) | Onboarding, regional installers, AppCloud, HONOR App Market, diagnostics, firmware-integrated features | These catalog entries appear in scans and are excluded from new disables. |

The disable path checks for installed, enabled system packages on Android user 0 and refuses packages with system UIDs, shared UIDs, persistent or required-for-system-user flags, overlays and declared shared libraries. Launcher, HONOR ID, system update, package installation, Play Services, Play Store, camera, networking and input components stay outside the disable allowlist. Catalog names are a starting point. Firmware dependencies can still affect features, and disabling packages provides no measurement of network traffic or performance. [Android's package-manager interface](https://developer.android.com/tools/adb#pm)

For a first run, choose **1 (Scan)** and **2 (Preview conservative)**. If HONOR Tips appears and you want to disable it, choose **3 (Apply conservative)** and review the confirmation. Restart the tablet when convenient and check Settings, Play Store, streaming, Wi-Fi, Bluetooth, camera, audio, sleep/wake and system updates. Use **7 (Restore last)** if you want to undo the change. Turn off USB debugging when finished.

## Commands

The WSL and macOS/Linux launcher also accepts commands directly:

```sh
./start_macos_linux.sh scan
./start_macos_linux.sh plan --profile safe
./start_macos_linux.sh apply --profile safe
./start_macos_linux.sh plan --profile privacy
./start_macos_linux.sh apply --profile privacy
./start_macos_linux.sh optional
./start_macos_linux.sh select com.hihonor.notepad
./start_macos_linux.sh restore
./start_macos_linux.sh restore --all
```

Put `--serial`, `--adb` and `--recovery-dir` **before** the command. Use `--serial SERIAL` when ADB sees several authorized devices. If your ADB backend omits the USB descriptor, disconnect any other USB ADB devices so the tool can verify which one is on the cable.

## Recovery and moving between PCs

Keep the `recovery/` folder beside the script. The tool records each tablet's USB serial hash and writes each journal entry before trying a change. A disconnected or unverified apply stops the batch. Reconnect the tablet by USB, then use `restore` for the latest pending operation or `restore --all` for the full journal history. Restore checks the current package state before acting and verifies the result afterward.

When changing PCs, copy the recovery folder with the project or point to the copied folder explicitly:

```sh
./start_macos_linux.sh --recovery-dir "/path/to/copied/recovery" restore
```

New journals preserve Android's original setting: `default-state` for apps using their manifest default, or `enable` for apps that were explicitly enabled. Version 1.0 journals only recorded effective enabled status, so restoring one uses `enable` if the package is still in the `disabled-user` state. MagicOS policy can reject a change. Keep the journal if recovery is interrupted or fails. Scans include installed package names and build details. Review a scan before sharing it.

## References

- [HONOR Pad X8a specifications](https://www.honor.com/mea/tablets/honor-pad-x8a/spec/), [HONOR NDL-W09 product sheet](https://www.honor.com/content/dam/honor/common/energy/product-information-sheet/german/HONOR%20Pad%20X8a_de.pdf), [HONOR NDL-L09 support](https://www.honor.com/my/support/tablets/honor-pad-x8a/) and [Bolivia ATT NDL-L03 certification](https://api.att.gob.bo/numequip/uploads/ATT-DTLTIC-RA-H-TL%20LP%20676_2024.PDF)
- [HONOR developer package names](https://developer.honor.com/cn/kitdoc/content/11106/guides/themetool.md) and [community HONOR catalog](https://github.com/PixelCode01/UIBloatwareRegistry/blob/main/Honor/honor-bloatware-list.md)
- [AOSP package settings and dump format](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-14.0.0_r1/services/core/java/com/android/server/pm/Settings.java) and [AOSP enabled-state commands](https://android.googlesource.com/platform/frameworks/base/+/771e5d913963ee62c1af494f0d4c78d5d18b3bc9/services/core/java/com/android/server/pm/PackageManagerShellCommand.java)

## Offline tests

```sh
python3 -m unittest discover -s tests -v
```

To report a problem, include the tool version (`--version`), host OS, tablet model and firmware build, and the exact error with any serial numbers removed. Keep full package inventories and recovery journals private. [GitHub Issues](https://github.com/jaysplen/honor_pad_x8a_debloater/issues/new)
