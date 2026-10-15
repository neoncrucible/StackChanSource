"""Actionable camera failures, without exposing network bodies or credentials."""
from __future__ import annotations
import http.client


MESSAGES = {
    'pairing_missing': 'UnitV2 is not paired with this Windows account. Use First-time setup once; app updates keep that pairing.',
    'pairing_rejected': 'UnitV2 pairing rejected. If setup just completed, restart UnitV2 once; otherwise use First-time setup / repair.',
    'challenge_expired': 'UnitV2 authentication timed out. The saved pairing has not been changed; try again.',
    'service_missing': 'UnitV2 answered, but its Kadence camera service is not running. If setup just completed, restart UnitV2 once; do not reinstall the app.',
    'service_incompatible': 'This address answered with a different camera service. Check the saved UnitV2 address.',
    'connection_refused': 'UnitV2 camera service is not accepting connections. It may still be starting; the saved pairing is intact.',
    'offline': 'UnitV2 is unreachable at the saved address. Check camera power and Wi-Fi; the saved setup is still intact.',
    'timeout': 'The camera did not respond before the deadline. Check its connection; you can retry now without running setup.',
    'frame_timeout': 'UnitV2 is connected, but its camera produced no fresh image. Reconnect the camera to restart capture.',
    'producer_exited': 'UnitV2 is connected, but its image process stopped. Reconnect the camera to restart capture.',
    'producer_stream_ended': 'UnitV2 is connected, but its image stream ended. Reconnect the camera to restart capture.',
    'start_failed': 'UnitV2 is connected, but its image process could not start. Reconnect the camera and check its live status.',
    'camera_owned': 'Another camera session is using UnitV2. Close that session, then reconnect the camera.',
    'other_camera_producer': 'Another camera process is running on UnitV2. Close any other preview; if it remains, restart UnitV2 once.',
    'lease_expired': 'The UnitV2 camera session expired. Ask again to start a fresh session; setup is retained.',
    'lease_revoked': 'The UnitV2 camera session ended. Ask again to start a fresh session; setup is retained.',
    'lease_mismatch': 'UnitV2 is using a different camera session. Reconnect the camera; pairing has not been lost.',
    'capture_cancelled': 'The UnitV2 image request ended before a fresh frame arrived. Try again.',
    'stop_unconfirmed': 'UnitV2 has not confirmed that capture stopped. Check its connection before starting another camera session.',
    'invalid_image': 'UnitV2 returned an unreadable image. The camera connection succeeded; image capture needs checking.',
    'invalid_response': 'The camera returned an invalid service response. Check the saved UnitV2 address and camera status.',
    'service_error': 'The camera request failed. Check the camera status for the failed stage; saved setup has not been cleared.',
}


class CameraFault(RuntimeError):
    def __init__(self, code):
        self.code = code if code in MESSAGES else 'service_error'
        super().__init__(MESSAGES[self.code])


def camera_fault(error):
    if isinstance(error, CameraFault): return error
    code = getattr(error, 'code', None)
    if code in MESSAGES: return CameraFault(code)
    if isinstance(error, TimeoutError): return CameraFault('timeout')
    if isinstance(error, ConnectionRefusedError): return CameraFault('connection_refused')
    if isinstance(error, (OSError, http.client.HTTPException)): return CameraFault('offline')
    if isinstance(error, ValueError): return CameraFault('invalid_response')
    return CameraFault('service_error')


def diagnostic_issue(value):
    if not isinstance(value, dict) or value.get('code') not in MESSAGES: return None
    return {'code': value['code'], 'source': 'unitv2-camera' if value.get('source') == 'unitv2-camera' else 'robot-camera'}
