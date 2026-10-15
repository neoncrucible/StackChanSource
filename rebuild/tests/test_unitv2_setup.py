import errno
import shlex
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from kcore.unitv2_setup import NULL_DEVICE_PREFLIGHT, preparation_command


@pytest.mark.parametrize('mode,device,expected', [
    (stat.S_IFCHR | 0o660, 0x103, 'repair'),
    (stat.S_IFCHR | 0o666, 0x103, 'unchanged'),
    (stat.S_IFREG | 0o660, 0, 'refuse'),
    (stat.S_IFCHR | 0o660, 0x105, 'refuse'),
])
def test_camera_null_preflight_repairs_only_linux_null(mode, device, expected):
    changes, closed = [], []
    remote_os = SimpleNamespace(
        O_RDONLY=0, O_NOFOLLOW=0x20000, O_NONBLOCK=0x800,
        open=lambda path, flags: 7,
        fstat=lambda fd: SimpleNamespace(st_mode=mode, st_rdev=device),
        makedev=lambda major, minor: (major << 8) | minor,
        fchmod=lambda fd, permissions: changes.append((fd, permissions)),
        close=closed.append,
    )
    with patch.dict(sys.modules, {'os': remote_os}):
        if expected == 'refuse':
            with pytest.raises(SystemExit, match='Unexpected /dev/null'):
                exec(NULL_DEVICE_PREFLIGHT, {})
        else:
            exec(NULL_DEVICE_PREFLIGHT, {})
    assert changes == ([(7, 0o666)] if expected == 'repair' else [])
    assert closed == [7]


def test_camera_null_preflight_refuses_symlink_without_chmod():
    def reject_symlink(path, flags):
        assert path == '/dev/null' and flags & 0x20000
        raise OSError(errno.ELOOP, 'Too many symbolic links')
    remote_os = SimpleNamespace(
        O_RDONLY=0, O_NOFOLLOW=0x20000, O_NONBLOCK=0x800,
        open=reject_symlink,
    )
    with patch.dict(sys.modules, {'os': remote_os}):
        with pytest.raises(OSError) as error:
            exec(NULL_DEVICE_PREFLIGHT, {})
    assert error.value.errno == errno.ELOOP


def test_remote_preflight_is_one_python_argument_and_staging_is_private():
    destination = '/tmp/kadence-setup-0123456789abcdef'
    args = shlex.split(preparation_command(destination))
    assert args[:4] == ['sudo', 'python3', '-c', NULL_DEVICE_PREFLIGHT]
    assert args[4:] == ['&&', 'test', '-r', '/dev/null', '&&', 'test', '-w',
                       '/dev/null', '&&', 'umask', '077', '&&', 'mkdir', destination]


def test_setup_address_is_shared_with_next_app_version_without_changing_privacy(tmp_path):
    from kcore.camera_manager import CameraConfig
    from kcore.unitv2_setup import save_address
    saved=CameraConfig(address='192.168.40.175',privacy=True,policy='OFF',source='unitv2-camera',greetings=True)
    saved.save(tmp_path)
    save_address('192.168.40.42',root=tmp_path)
    reopened=CameraConfig.load(tmp_path)
    assert reopened.address=='192.168.40.42'
    assert reopened.privacy and reopened.policy=='OFF' and reopened.greetings
    assert reopened.source=='unitv2-camera'


def test_default_setup_reuses_saved_connection_without_ssh_or_writing_pairing(tmp_path):
    import ctypes
    from unittest.mock import Mock
    from kcore import unitv2_setup as setup
    from kcore.camera_manager import CameraConfig
    vault=Mock();vault.load.return_value={'unitv2_token':'ab'*32}
    windows=SimpleNamespace(kernel32=SimpleNamespace(GetConsoleWindow=lambda:0))
    with patch.object(setup,'os',SimpleNamespace(name='nt')), \
         patch.object(ctypes,'windll',windows,create=True), \
         patch('kcore.unitv2_lifecycle.pairing_vault',return_value=vault), \
         patch('kcore.storage.default_data_dir',return_value=tmp_path), \
         patch('builtins.input',side_effect=['','192.168.40.42','']), \
         patch.object(setup,'check_existing',return_value={'version':'1.3.0','state':'STOPPED'}) as check, \
         patch.object(setup.subprocess,'run',side_effect=AssertionError('Must not run SSH')):
        assert setup.main()==0
    check.assert_called_once_with('192.168.40.42','ab'*32)
    vault.save.assert_not_called();vault.forget.assert_not_called()
    assert CameraConfig.load(tmp_path).address=='192.168.40.42'
