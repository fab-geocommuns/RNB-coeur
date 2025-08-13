import sys
from typing import List

from django.contrib.gis.db import models


def is_model_code(code: str) -> bool:
    try:
        _verify_code(code)
    except ValueError:
        return False

    return True


def model_to_code(m: models.Model) -> str:
    if not isinstance(m, models.Model):
        raise ValueError(f"Expected a model, got {type(m)}")

    return f"model:{m.__class__.__name__}:{m.pk}"


def code_to_pk(code: str) -> int:
    _verify_code(code)

    _, cls_name, pk = _code_parts(code)

    return int(pk)


def code_to_cls_name(code: str) -> str:
    _verify_code(code)

    _, cls_name, pk = _code_parts(code)

    return cls_name


def code_to_cls(code: str) -> type[models.Model]:
    _verify_code(code)

    _, cls_name, pk = _code_parts(code)

    return _cls_name_to_cls(cls_name)


def code_to_model(code: str) -> models.Model:
    _verify_code(code)

    _, cls_name, pk = _code_parts(code)

    cls = _cls_name_to_cls(cls_name)

    return cls.objects.filter(pk=pk).first() # type: ignore[return-value]


def _cls_name_to_cls(cls_name: str) -> type[models.Model]:
    try:
        cls = sys.modules["batid.models"].__dict__[cls_name]
    except AttributeError:
        raise ValueError(f"Unknown model class {cls_name} in batid.models")

    return cls


def _verify_code(code: str) -> None:
    _raise_unless_str(code)
    _raise_unless_model_code(code)
    _raise_unless_length(code)


def _code_parts(code: str) -> List[str]:
    return code.split(":")


def _raise_unless_length(code: str) -> None:
    if len(code.split(":")) != 3:
        raise ValueError(f'Expected a code with 3 parts separated with ":", got {code}')


def _raise_unless_str(code: str) -> None:
    if not isinstance(code, str):
        raise ValueError(f"Expected a string, got {type(code)}")


def _raise_unless_model_code(code: str) -> None:
    if not code.startswith("model:"):
        raise ValueError(f"Expected a code starting with 'model:', got {code}")
