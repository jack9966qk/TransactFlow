from typing import Dict
from base import *
from datetime import date
import json

def ConvertObject(obj):
    if type(obj) is Transaction:
        d = { k:v for k, v in obj.__dict__.items() }
        (filename, line) = d["sourceLocation"]
        d["sourceLocation"] = { "filename": filename, "line": line }
        return d
    if type(obj) is Category:
        return obj.label
    if type(obj) is date:
        return f"{obj}"
    json.dumps(obj)

def CategoryKeysToLabels(dictionary):
    return {
        (k if type(k) is not Category else k.label): v
        for k, v in dictionary.items()
    }

def buildLabelToCategoryMap() -> Dict[str, Category]:
    return { c.label: c for c in ORDERED_BASE_CATEGORIES }

labelsToCategories = buildLabelToCategoryMap()

def categoryForLabel(label: str) -> Category:
    return labelsToCategories[label]