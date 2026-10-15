"""Natural camera requests with explicit, conservative setting-change authority."""
from __future__ import annotations
import re

CAMERA_CHANGES = {
    "privacy_on": "turn camera privacy on", "privacy_off": "turn camera privacy off",
    "perception_on": "enable automatic perception", "perception_off": "disable automatic perception",
    "greetings_on": "enable greetings", "greetings_off": "disable greetings",
    "unitv2": "use the UnitV2 camera", "robot": "use the StackChan camera", "auto": "select the camera automatically",
    "stop": "stop the UnitV2 camera", "on_demand": "use the UnitV2 camera on demand",
    "keep_ready": "keep the UnitV2 camera ready", "aware": "use AWARE perception mode",
    "event_only": "use event-only perception mode",
}


def normalise_request(text):
    normal = text.casefold().replace("’", "'")
    normal = re.sub(r"[.!?,;:]", " ", normal)
    normal = re.sub(r"\s+", " ", normal).strip()
    # Strip conversational wrappers, never negate or repair an action verb.
    for _ in range(5):
        previous = normal
        normal = re.sub(r"^(?:(?:hey |okay |ok )?(?:kadence|kade)\b|please\b)\s*", "", normal)
        normal = re.sub(r"^(?:(?:can|could|would|will) you(?: please)? |i (?:want|need) you to )(?=(?:tell|show|describe|look|read|identify|track|follow|keep|stop|start|turn|enable|disable|use|switch)\b)", "", normal)
        normal = re.sub(r"\s+(?:for me(?: please)?|please(?: now)?|now)$", "", normal).strip()
        if normal == previous:
            break
    return normal


def is_visual_request(text):
    """A request for current visual evidence, not a general knowledge question."""
    normal = normalise_request(text)
    normal = re.sub(r"^(?:tell me |show me )", "", normal)
    if re.match(r"^(?:don't|do not|never|stop|if|when|how (?:do|can))\b", normal):
        return False
    patterns = (
        r"what (?:can|do) you see\b",
        r"what (?:are you|you're) looking at\b",
        r"what (?:am i|i'm) holding\b",
        r"what(?:'s| is) (?:this|that|in (?:front of you|your view)|on (?:my|the) desk)\b",
        r"(?:look at|have a look at|take a look at) (?:this|that|the|my)\b",
        r"(?:describe|identify|read|scan) (?:this|that)\b",
        r"describe what (?:you|i)\b",
        r"(?:describe|identify) (?:the |my )?(?:view|scene|room|desk|object|item|person|thing|colour|color|shape)\b",
        r"(?:read|scan) (?:the |my )?(?:label|text|code|qr|barcode|sign|writing)\b",
        r"(?:what|which) colou?r (?:(?:is|are) )?(?:this|that|it|these|those|the|my)\b",
        r"(?:the )colou?r of (?:this|that|it|these|those|the|my)\b",
        r"what shape (?:(?:is|are) )?(?:this|that|it|these|those|the|my)\b",
        r"(?:can you )see (?:what|this|that|the|my)\b",
    )
    return any(re.match(pattern, normal) for pattern in patterns)


def camera_plan(text):
    normal = normalise_request(text)
    if is_visual_request(text):
        return {"tool":"desk_look","arguments":{"question":text}}
    if normal in {"camera status", "which camera are you using", "what cameras do you have", "do you have a camera", "is your camera on", "are you looking", "can you use the extra camera", "do you have an extra camera", "is automatic perception on", "why aren't you greeting me"}:
        return {"tool":"camera_status","arguments":{}}
    if normal in {'tracking status','are you tracking','what are you tracking'}:
        return {'tool':'tracking_status','arguments':{}}
    if re.fullmatch(r'stop (?:object tracking|tracking|following)(?: .{1,80})?', normal):
        return {'tool':'tracking_control','arguments':{'action':'stop'}}
    match=re.fullmatch(r'(?:follow|track|keep track of|keep an eye on) (.{1,80})',normal)
    if match:
        return {'tool':'tracking_control','arguments':{'action':'follow','target':match[1]}}
    if normal in {'stop factory vision','stop factory mode','stop shape recognition','stop colour tracking','stop color tracking'}:
        return {'tool':'factory_vision','arguments':{'action':'stop'}}
    factory_phrases = {
        'shape recognition':'shape_detector','shape detection':'shape_detector',
        'colour tracking':'color_tracker','color tracking':'color_tracker',
        'motion detection':'motion_tracker','motion tracking':'motion_tracker',
        'code detection':'code_detector','object recognition':'object_recognition',
        'face detection':'face_detector','lane tracking':'lane_line_tracker',
        'online classifier':'online_classifier','audio fft':'audio_fft',
    }
    for phrase, mode in factory_phrases.items():
        if normal in {'start '+phrase,'use '+phrase,'enable '+phrase}:
            return {'tool':'factory_vision','arguments':{'action':'start','mode':mode}}
    if normal in {'factory vision status','factory mode status','what factory mode is running'}:
        return {'tool':'factory_vision','arguments':{'action':'status'}}
    phrases = {
        "privacy_on": {"turn privacy on","enable camera privacy","turn camera privacy on","stop looking"},
        "privacy_off": {"turn privacy off","disable camera privacy","turn camera privacy off"},
        "perception_on": {"enable automatic perception","turn on automatic perception","start automatic perception"},
        "perception_off": {"disable automatic perception","turn off automatic perception","stop automatic perception"},
        "greetings_on": {"enable greetings","turn on greetings","turn greetings on"},
        "greetings_off": {"disable greetings","turn off greetings","turn greetings off"},
        "unitv2": {"use the unitv2 camera","use the unit v2 camera","use the unit v two camera","use the extra camera","switch to extra camera","switch to the extra camera","switch to the unitv2 camera","switch to the unit v2 camera","switch to the unit v two camera"},
        "robot": {"use the robot camera","use the stackchan camera","use the built in camera","switch to the robot camera","switch to the built in camera"},
        "auto": {"select the camera automatically","use automatic camera selection"},
        "stop": {"stop the camera","stop the unitv2 camera","stop the unit v2 camera"},
        "on_demand": {"start the camera","use the camera on demand","use the unitv2 camera on demand"},
        "keep_ready": {"keep the camera ready","keep the unitv2 camera ready"},
        "aware": {"use aware mode","enable aware mode","use aware perception mode"},
        "event_only": {"use event only mode","use event-only perception mode"},
    }
    for command, options in phrases.items():
        if normal in options: return {"tool":"camera_control","arguments":{"command":command}}
    return None
