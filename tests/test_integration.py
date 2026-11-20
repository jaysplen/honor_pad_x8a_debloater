"""End-to-end dry system-state simulation; no tablet or ADB needed."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import honor_x8a_debloater as d

class FakeDevice:
    def __init__(self, recovery_dir):
        self.properties = {"ro.product.model": "NDL-W09", "ro.product.manufacturer": "HONOR"}
        self.device_key = 'fake-device'
        self.recovery_dir = recovery_dir
        self.active = {'com.hihonor.tips', 'com.facebook.services', 'com.hihonor.hiviewtunnel',
                       'com.hihonor.android.launcher', 'com.google.android.gms'}
        self.disabled = {'com.hihonor.magazine'}
        self.system = self.active | self.disabled
        self.blocked = set()
        self.interrupted = set()
        self.settings = {pkg: 0 for pkg in self.active} | {pkg: 3 for pkg in self.disabled}
        self.writes = []

    def require_writable(self):
        assert d.recognized_device(self.properties)

    def packages(self, *switches, package=None):
        if '-e' in switches:
            result = self.active
        elif '-d' in switches:
            result = self.disabled
        elif '-s' in switches:
            result = self.system
        else:
            result = self.active | self.disabled
        return {pkg for pkg in result if package is None or package in pkg}

    def package_state(self, package):
        return d.PackageState(self.settings[package], package in self.system, False)

    def inventory(self):
        return {'installed': self.packages(), 'enabled': self.packages('-e'),
                'disabled': self.packages('-d'), 'system': self.packages('-s')}

    def shell(self, *parts):
        tool, verb, user_flag, user, pkg = parts
        assert (tool, user_flag, user) == ('pm', '--user', '0')
        self.writes.append((pkg, verb))
        if pkg in self.blocked:
            raise RuntimeError('Fake SecurityException')
        if verb == 'disable-user':
            self.active.remove(pkg)
            self.disabled.add(pkg)
            self.settings[pkg] = 3
            if pkg in self.interrupted:
                raise subprocess.TimeoutExpired(verb, 35)
        elif verb in {'enable', 'default-state'}:
            self.disabled.remove(pkg)
            self.active.add(pkg)
            self.settings[pkg] = 1 if verb == 'enable' else 0
        else:
            raise AssertionError('unexpected call')
        return f'Package {pkg}: {verb}'

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.device = FakeDevice(self.directory)

    def apply_with_confirmation(self, items):
        with patch('builtins.input', return_value=f'DISABLE {len(items)}'), contextlib.redirect_stdout(io.StringIO()):
            return d.do_apply(self.device, items, 'safe')

    def test_apply_restore_preserves_already_disabled_apps(self):
        items, _ = d.selection(self.device.inventory(), 'safe')
        self.assertEqual([t.package for t in items], ['com.hihonor.tips'])
        self.apply_with_confirmation(items)
        self.assertIn('com.hihonor.tips', self.device.disabled)
        self.assertIn('com.hihonor.magazine', self.device.disabled)
        self.assertIn('com.hihonor.android.launcher', self.device.active)
        with patch('builtins.input', return_value='RESTORE 1'), contextlib.redirect_stdout(io.StringIO()):
            d.restore(self.device, last=True)
        self.assertIn('com.hihonor.tips', self.device.active)
        self.assertEqual(self.device.settings['com.hihonor.tips'], 0)
        self.assertIn(('com.hihonor.tips', 'default-state'), self.device.writes)
        self.assertIn('com.hihonor.magazine', self.device.disabled)
        with contextlib.redirect_stdout(io.StringIO()):
            d.restore(self.device, last=True)
        self.assertIn('com.hihonor.tips', self.device.active)

    def test_privacy_opt_in_cannot_execute_without_confirmation(self):
        items, _ = d.selection(self.device.inventory(), 'privacy')
        self.assertEqual({t.package for t in items}, {'com.hihonor.tips', 'com.facebook.services'})
        with patch('builtins.input', return_value='WRONG'), contextlib.redirect_stdout(io.StringIO()):
            d.do_apply(self.device, items, 'privacy')
        self.assertIn('com.hihonor.tips', self.device.active)
        self.assertIn('com.hihonor.hiviewtunnel', self.device.active)
        self.assertIn('com.facebook.services', self.device.active)
        self.assertFalse(list(self.directory.glob('transaction_*.json')))

    def test_failed_disable_stops_and_keeps_journal(self):
        self.device.blocked.add('com.hihonor.tips')
        items, _ = d.selection(self.device.inventory(), 'safe')
        self.assertFalse(self.apply_with_confirmation(items))
        journals = list(self.directory.glob('transaction_*.json'))
        self.assertEqual(len(journals), 1)
        txn = json.loads(journals[0].read_text())
        self.assertEqual(txn['status'], 'partial')
        self.assertIn('com.hihonor.tips', self.device.active)

    def test_restore_after_disable_acknowledgement_is_lost(self):
        pkg = 'com.hihonor.tips'
        self.device.settings[pkg] = 1
        self.device.interrupted.add(pkg)
        items, _ = d.selection(self.device.inventory(), 'safe')
        self.assertFalse(self.apply_with_confirmation(items))
        record = json.loads(next(self.directory.glob('transaction_*.json')).read_text())
        self.assertEqual(record['changes'][0]['status'], 'unverified')
        with patch('builtins.input', return_value='RESTORE 1'), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(d.restore(self.device, last=True))
        self.assertEqual(self.device.settings[pkg], 1)
        self.assertEqual(self.device.writes, [(pkg, 'disable-user'), (pkg, 'enable')])

    def write_legacy_journal(self, pkg):
        d.write_json(self.directory / 'transaction_legacy.json', {
            'version': '1.0.0', 'device_key': self.device.device_key, 'method': 'pm disable-user --user 0',
            'changes': [{'package': pkg, 'before': 'enabled', 'status': 'disabled'}],
        })

    def test_legacy_journal_supports_formerly_eligible_app(self):
        pkg = 'com.hihonor.hiviewtunnel'
        self.device.active.remove(pkg)
        self.device.disabled.add(pkg)
        self.device.settings[pkg] = 3
        self.write_legacy_journal(pkg)
        with patch('builtins.input', return_value='RESTORE 1'), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(d.restore(self.device, last=True))
        self.assertEqual(self.device.writes, [(pkg, 'enable')])

    def test_journal_cannot_target_protected_package(self):
        self.write_legacy_journal('com.hihonor.android.launcher')
        with self.assertRaisesRegex(RuntimeError, 'Invalid or ineligible change'):
            d.restore(self.device, last=True)
        self.assertFalse(self.device.writes)

    def test_apply_requires_written_journal(self):
        items, _ = d.selection(self.device.inventory(), 'safe')
        with patch.object(d, 'write_json', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.apply_with_confirmation(items)
        self.assertFalse(self.device.writes)

    def test_another_tablet_cannot_restore_this_journal(self):
        items, _ = d.selection(self.device.inventory(), 'safe')
        self.assertTrue(self.apply_with_confirmation(items))
        self.device.device_key = 'another-tablet'
        with patch('builtins.input', side_effect=AssertionError('Unexpected prompt')), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(d.restore(self.device, last=False))
        self.assertEqual(self.device.writes, [('com.hihonor.tips', 'disable-user')])

    def test_restore_preserves_later_external_state(self):
        pkg = 'com.hihonor.tips'
        items, _ = d.selection(self.device.inventory(), 'safe')
        self.assertTrue(self.apply_with_confirmation(items))
        self.device.settings[pkg] = 2
        with patch('builtins.input', return_value='RESTORE 1'), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(d.restore(self.device, last=True))
        self.assertEqual(self.device.settings[pkg], 2)
        self.assertEqual(self.device.writes, [(pkg, 'disable-user')])

@unittest.skipUnless(sys.platform == "win32", "Requires Windows cmd.exe")
class WindowsLauncherTests(unittest.TestCase):
    def test_launcher_forwards_arguments_and_exit_code_from_a_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            project = work / "HONOR Pad X8a"
            project.mkdir()
            launcher = project / "Start_Windows.bat"
            shutil.copyfile(d.BASE / launcher.name, launcher)
            shutil.copyfile(d.BASE / "honor_x8a_debloater.py", project / "honor_x8a_debloater.py")
            command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "call", str(launcher)]
            options = {"cwd": work, "stdin": subprocess.DEVNULL, "capture_output": True, "text": True, "timeout": 30}

            version = subprocess.run([*command, "--version"], **options)
            self.assertEqual(version.returncode, 0, version.stderr)
            self.assertEqual(version.stdout.strip(), f"honor_x8a_debloater.py {d.VERSION}")

            missing_adb = project / "missing adb.exe"
            scan = subprocess.run([*command, "--adb", str(missing_adb), "scan"], **options)
            self.assertEqual(scan.returncode, 1, scan.stderr)
            self.assertIn("ADB executable not found", scan.stderr)
            self.assertIn(missing_adb.name, scan.stderr)


if __name__ == '__main__':
    unittest.main()
