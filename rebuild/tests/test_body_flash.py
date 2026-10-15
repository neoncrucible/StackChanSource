import hashlib
import json
from pathlib import Path

import pytest

from kcore.body_flash import flash, verified_files


COMMIT='a'*40


@pytest.fixture
def firmware(tmp_path):
    root=tmp_path/'Firmware';root.mkdir()
    files={'0x0':'bootloader.bin','0x8000':'partitions.bin','0x10000':'app.bin'}
    entries={}
    for offset,name in files.items():
        data=name.encode()*5;(root/name).write_bytes(data)
        entries[name]={'offset':offset,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    (root/'RELEASE.json').write_text(json.dumps({'device':'CoreS3-StackChan','firmware_version':'0.21.7','chip':'esp32s3','flash_size':'16MB','source_commit':COMMIT,'files':entries}))
    (root/'flasher_args.json').write_text(json.dumps({'extra_esptool_args':{'chip':'esp32s3'},'flash_settings':{'flash_mode':'qio','flash_freq':'80m','flash_size':'16MB'},'flash_files':files}))
    return root


def test_update_backs_up_and_verifies_nvs_without_erasing_or_writing_it(firmware,tmp_path):
    calls=[]
    def runner(args):
        calls.append(args)
        if 'read_flash' in args:Path(args[-1]).write_bytes(b'x'*0x4000)
    backup=flash(firmware,COMMIT,'COM4',tmp_path/'backups',runner=runner)
    assert len(calls)==3
    write=calls[1]
    assert 'write_flash' in write and 'erase_flash' not in str(calls)
    assert '0x9000' not in write and '0xc10000' not in write
    assert write[write.index('--after')+1]=='no_reset'
    assert json.loads((backup/'update.json').read_text())['settings_preserved'] is True


@pytest.mark.parametrize('issue',['changed_image','wrong_commit','wrong_device','nvs_offset','traversal','bad_port'])
def test_bad_packages_never_contact_a_device(firmware,tmp_path,issue):
    manifest=json.loads((firmware/'flasher_args.json').read_text())
    release=json.loads((firmware/'RELEASE.json').read_text())
    if issue=='changed_image':(firmware/'app.bin').write_bytes(b'bad')
    if issue=='wrong_device':release['device']='StickS3'
    if issue=='nvs_offset':manifest['flash_files']['0x9000']='app.bin'
    if issue=='traversal':manifest['flash_files']['0x10000']='../app.bin'
    (firmware/'RELEASE.json').write_text(json.dumps(release));(firmware/'flasher_args.json').write_text(json.dumps(manifest))
    calls=[]
    with pytest.raises(ValueError):flash(firmware,'b'*40 if issue=='wrong_commit' else COMMIT,'bad' if issue=='bad_port' else 'COM4',tmp_path/'backup',runner=calls.append)
    assert not calls


def test_failed_backup_prevents_firmware_write(firmware,tmp_path):
    calls=[]
    with pytest.raises(ValueError,match='back up'):
        flash(firmware,COMMIT,'COM4',tmp_path/'backup',runner=calls.append)
    assert len(calls)==1 and 'read_flash' in calls[0]


def test_settings_mismatch_is_reported_after_write(firmware,tmp_path):
    calls=[]
    def runner(args):
        calls.append(args)
        if 'read_flash' in args:Path(args[-1]).write_bytes((b'a' if len(calls)==1 else b'b')*0x4000)
    with pytest.raises(RuntimeError,match='verification failed'):
        flash(firmware,COMMIT,'COM4',tmp_path/'backup',runner=runner)
    assert len(calls)==3
