# UnitV2-M12 Wi-Fi bring-up — 2026-09-20

Architecture: separate USB 5V power, UnitV2 Wi-Fi to Windows host. CoreS3
serial/voice/sensors unchanged. UART experiment remains untouched; no UART work.
Gesture and ToF physical baseline: SENSOR_PHYSICAL_SIGNOFF_2026-09-17.md.

## Physical evidence

- Factory recovery ZIP extracted on Windows; M5UnitV2UpdPackage.img 322662424 bytes.
- ZIP SHA256 C36022A56F101608625571115A9C0165F9A203151B58F69E1379EE53483F88DA
  records the downloaded file, not independent publisher verification.
- Original /etc archived to SD and copied to Windows; etc.tar SHA256
  3A4204E9CCCA2850DC11FE4D6F26EF954E88382E2AEF003E251BD989D88F5F4E.
  Sensitive backup stays local, never commit it. This is a configuration backup,
  not a full NAND image. Recovery package has not been flashed/tested.
- Linux 4.9.84, Buildroot 2020.02.8; root UBIFS, FAT32 SD.
- Factory /dev/null was 0660 root:root, preventing SCP; corrected to 0666.
  Persistence of that correction across boot was not tested.
- Existing S90wifi-conf starts wpa_supplicant on wlan0; existing dhcpcd handles
  wlan0 and excludes eth0, wlan1, br0. No startup scripts needed changing.
- Credentials provisioned locally using wpa_passphrase, removing plaintext
  password comment. /etc/wpa_supplicant.conf mode 0600. SSID case matters.
- WPA2 association, DHCP, browser live video confirmed. Two complete cold boots
  on separate USB power restored Wi-Fi and moving video without credentials.
- Tested address 192.168.40.175 is DHCP-assigned, not a reserved/static address.
  Reserve the camera address at the router before treating it as stable.

## API evidence from device UI and live HTTP

Uploaded factory HTML and JavaScript inspected; no guessed routes:

- GET /video_feed: HTTP/1.0 200; multipart/x-mixed-replace; boundary=frame.
  Three-second sample transferred 1926845 bytes. Timeout was deliberate.
- POST /get_last_func returned last_func=camera_stream, title=Camera Stream,
  description=480P real-time video preview.
- JS selects mode via POST /func JSON:
  {"type_id":"3","type_name":"camera_stream","args":""}.
  Initial diagnostic did not select mode; see the 2026-09-21 correction below.
- UI snapshots copy canvas pixels locally, not a separate snapshot endpoint.
- POST /func/result and /render_items provide separate pipe-delimited streams.
  Recognition/behaviour integration is deferred.

## First host gate

Run while normal Kadence is open; no COM port is opened by this diagnostic:

```powershell
Set-Location 'C:\KadenceX\source\rebuild'
uv run --no-project --python 3.12 --with 'Pillow>=11,<13' .\tools\unitv2_network_status.py --address 192.168.40.175 --count 3
```

Client opens a fresh connection per sample, checks multipart/JPEG framing, caps
headers and JPEG size, applies socket timeouts and a body deadline, closes the
stream, and decodes with Pillow. No files saved, cloud calls, serial commands,
recognition, automatic actions or desktop UI changes. Six local transport tests
pass. Physical JPEG decoding, coexistence and desktop integration remain pending.

## 2026-09-21: browser startup dependency found and addressed

Cold camera accepted TCP but /video_feed returned no HTTP headers or bytes in
8 seconds. Opening the factory UI and selecting Camera Stream enabled capture:
three decoded 320x240 JPEGs, 26319/26271/26279 bytes, 0.125/0.046/0.063 seconds,
with distinct hashes. Thus earlier cold-boot signoff establishes Wi-Fi and video
AFTER UI activation; it does not establish unattended camera-producer startup.
The actual returned frame dimensions are QVGA despite UI description saying 480P.

Diagnostic now explicitly POSTs the factory /func camera_stream payload once
before sampling (overrides any currently selected recognition mode). It does not
write boot settings. Low-level capture_jpeg remains a read-only frame request.
Mode request success is not labelled readiness; only decoded frames are PASS.
First frame gets 15 seconds, subsequent frames 5 seconds. Startup HTTP failures
are reported. Eight local transport tests pass, including a producer that rejects
capture until the correct mode POST. The three successful hardware captures above
predate this startup fix; the fix itself still needs a browser-free cold-boot test.

Close browser camera tabs, power-cycle UnitV2, allow a minute for Wi-Fi, then run
the same diagnostic command without visiting the web UI. No firmware flash needed.
Desktop UI integration and simultaneous robot voice/sensor verification remain pending.
