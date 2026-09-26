"""Narrow voice intents. Model proposals cannot authorize camera setting changes."""
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


def camera_plan(text):
    normal = re.sub(r"[.!?,]", "", text.casefold()).strip()
    normal = re.sub(r"^(?:kadence |please )| please$", "", normal).strip()
    if normal in {"what can you see", "what do you see", "what am i holding", "describe what you see", "look at this", "read this"}:
        return {"tool":"desk_look","arguments":{"question":text}}
    if normal in {"camera status", "which camera are you using", "what cameras do you have", "do you have a camera", "is your camera on", "are you looking", "can you use the extra camera", "do you have an extra camera", "is automatic perception on", "why aren't you greeting me"}:
        return {"tool":"camera_status","arguments":{}}
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
