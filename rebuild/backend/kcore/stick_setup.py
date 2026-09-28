"""Provision only firmware which explicitly identifies as the Kadence StickS3."""
import ipaddress
import json
import re
import time


def provision(args,pairing):
    import serial
    if set(args)!={'port','ssid','password','host'}:raise ValueError('Invalid Stick pairing fields.')
    port=args['port'];ssid=args['ssid'];password=args['password'];host=args['host']
    if not isinstance(port,str) or not re.fullmatch(r'COM\d{1,3}|/dev/(ttyUSB|ttyACM)\d+',port,re.I):raise ValueError('Choose the StickS3 serial port.')
    if not isinstance(ssid,str) or not 1<=len(ssid.encode())<=32 or not isinstance(password,str) or len(password.encode())>63:raise ValueError('Check the Wi-Fi name and password.')
    from .audio_network import address_is_local
    address=ipaddress.IPv4Address(host)
    if address.is_loopback or address.is_unspecified or address.is_multicast or not address_is_local(host):raise ValueError('Select this PC LAN IPv4 address before pairing.')
    def receive(link,kind,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            raw=link.read_until(b'\n',2048)
            try:value=json.loads(raw)
            except (ValueError,UnicodeError):continue
            if isinstance(value,dict) and value.get('type')==kind:return value
        raise RuntimeError('Stick did not confirm pairing. Check its firmware and USB port.')
    with serial.Serial(port,115200,timeout=.2,write_timeout=2) as link:
        time.sleep(1)
        link.reset_input_buffer();link.write(b'{"type":"kadence.remote.probe"}\n');link.flush()
        value=receive(link,'kadence.remote.identity',5)
        if value.get('device')!='StickS3' or value.get('protocol')!=1:raise RuntimeError('This is not compatible StickS3 remote firmware.')
        config={'type':'kadence.remote.configure','ssid':ssid,'password':password,'host':host,'port':8766,**pairing}
        link.write((json.dumps(config)+'\n').encode());link.flush()
        value=receive(link,'kadence.remote.configured',8)
        if value.get('device_id')!=pairing['device_id'] or value.get('ok') is not True:raise RuntimeError('Stick configuration was not saved.')
