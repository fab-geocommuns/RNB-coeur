import sys

from django.contrib.gis.db import models


def model_to_code(m: models.Model) -> str:
    if not isinstance(m, models.Model):
        raise ValueError(f"Expected a model, got {type(m)}")

    return f"model:{m.__class__.__name__}:{m.pk}"


def code_to_model(code: str) -> models.Model:
    if not isinstance(code, str):
        raise ValueError(f"Expected a string, got {type(code)}")

    if not code.startswith("model:"):
        raise ValueError(f"Expected a code starting with 'model:', got {code}")

    parts = code.split(":")
    if len(parts) != 3:
        raise ValueError(f"Expected a code with 3 parts, got {code}")

    cls_name = parts[1]
    pk = parts[2]

    try:
        cls = sys.modules["batid.models"].__dict__[cls_name]
    except AttributeError:
        raise ValueError(f"Unknown model class {cls_name} in batid.models")

    try:
        return cls.objects.get(pk=pk)
    except cls.DoesNotExist:
        raise ValueError(f"Unknown model {cls_name} with pk {pk}")
