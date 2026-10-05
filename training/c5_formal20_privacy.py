"""Isolated headless research scene admission; never product minimization.

The prompt bytes are unchanged. Structural JSON keys are not customer labels.
Only default/public C5 fixture labels are admitted, with the ordinary privacy
classifier applied to task text and every string value. No redact-and-send.
This policy must be source-frozen and approved with the new formal study.
"""
import re

from agent.privacy import classify_request, PrivacyAction
from training.c5_rhino_adapter import step_input

LABEL = re.compile(r'(?:Default|C5-[A-Za-z0-9_-]{1,64})\Z')


def allowed(task, scene):
    step_input(task, scene)  # Exact, GUID-free, bounded semantic schema.
    if classify_request(task).action is not PrivacyAction.ALLOW_CLOUD:
        return False
    labels = [o['layer'] for o in scene['objects']] + list(scene['groups'])
    if any(not LABEL.fullmatch(label) for label in labels):
        return False
    def strings(value):
        if isinstance(value, str): yield value
        elif isinstance(value, dict):
            for item in value.values(): yield from strings(item)
        elif isinstance(value, list):
            for item in value: yield from strings(item)
    return all(classify_request(value).action is PrivacyAction.ALLOW_CLOUD for value in strings(scene))
