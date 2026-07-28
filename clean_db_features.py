import json
import ast
import re
from payment.models import SubscriptionPlan

def clean_f(data):
    if not data:
        return []
    if isinstance(data, str):
        data = data.strip()
        if not data:
            return []
        if (data.startswith('[') and data.endswith(']')) or (data.startswith('{') and data.endswith('}')):
            try:
                return clean_f(json.loads(data))
            except Exception:
                try:
                    return clean_f(ast.literal_eval(data))
                except Exception:
                    pass
        if '\n' in data:
            res = []
            for line in data.split('\n'):
                res.extend(clean_f(line))
            return res
        if ',' in data and ("'" in data or '"' in data):
            parts = re.findall(r"['\"]([^'\"]+)['\"]", data)
            if parts:
                return [p.strip() for p in parts if p.strip()]
        cleaned = data.strip("'\"\\ ").strip()
        return [cleaned] if cleaned else []
    if isinstance(data, list):
        res = []
        for item in data:
            for f in clean_f(item):
                if f and f not in res:
                    res.append(f)
        return res
    return [str(data).strip()]

for plan in SubscriptionPlan.objects.all():
    plan.features = clean_f(plan.features)
    plan.save()
    print(f"Cleaned Plan {plan.id} ({plan.name}): {len(plan.features)} items -> {plan.features}")
