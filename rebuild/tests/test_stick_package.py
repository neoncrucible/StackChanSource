"""Reject the ROM-header corruption that caused the first Stick hardware boot loop."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('package_sticks3',Path(__file__).resolve().parents[1]/'tools'/'package_sticks3.py')
packager=importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


@pytest.fixture
def image_parts(tmp_path):
    parts={}
    merged=bytearray(b'\xff'*0x10100)
    for offset,data in {0:bytes([0xe9,3,2,0x3f])+bytes(28),0x8000:b'partition-table',
                        0xe000:b'ota-selection',0x10000:b'application-image'}.items():
        path=tmp_path/str(offset)
        path.write_bytes(data)
        parts[offset]=path
        merged[offset:offset+len(data)]=data
    image=tmp_path/'merged.bin'
    image.write_bytes(merged)
    return image,parts


def test_preserved_compiler_components_pass(image_parts):
    packager.verify_merged_image(*image_parts)


def test_qio_rewrite_rejected_before_publication(image_parts):
    image,parts=image_parts
    corrupted=bytearray(image.read_bytes())
    corrupted[2]=0  # Exactly the former --flash_mode qio packaging rewrite.
    image.write_bytes(corrupted)
    with pytest.raises(ValueError,match='DIO ROM boot header'):
        packager.verify_merged_image(image,parts)


@pytest.mark.parametrize('offset',[3,0x8000,0xe000,0x10000])
def test_header_and_component_corruption_rejected(image_parts,offset):
    image,parts=image_parts
    corrupted=bytearray(image.read_bytes())
    corrupted[offset]^=1
    image.write_bytes(corrupted)
    with pytest.raises(ValueError,match='component differs'):
        packager.verify_merged_image(image,parts)


def test_incompatible_compiler_boot_header_rejected(image_parts):
    image,parts=image_parts
    boot=bytearray(parts[0].read_bytes())
    boot[2]=0
    parts[0].write_bytes(boot)
    with pytest.raises(ValueError,match='ROM bootloader must use a DIO'):
        packager.verify_merged_image(image,parts)


@pytest.mark.parametrize('wired',[False,True])
def test_microphone_definition_without_board_registration_is_rejected(tmp_path,wired):
    driver=tmp_path/'M5Unified.cpp'
    # Merely having the callback definition (as in 0.2.12) is insufficient.
    driver.write_text('bool M5Unified::_microphone_enabled_cb_sticks3(void*,bool) {}\n'
        'bool(*mic_enable_cb)(void*, bool) = nullptr;\n'
        'case board_t::board_M5StickS3: if (cfg.internal_mic) {\n'
        'mic_cfg.i2s_port = I2S_NUM_1;\n'+
        ('mic_enable_cb = _microphone_enabled_cb_sticks3;\n' if wired else '')+'} break;\n')
    if wired:packager.verify_microphone_driver(driver)
    else:
        with pytest.raises(ValueError,match='does not enable the microphone codec'):
            packager.verify_microphone_driver(driver)
