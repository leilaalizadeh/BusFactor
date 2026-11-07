# data/demo — SYNTHETIC DEMO DATA

Everything in this folder is **fictional** and exists only so BusFactor can be demonstrated offline.
No real students, patients or results are described. Owner: Teammate 1.

| File | Contents | Model (models.py) |
|---|---|---|
| `project_report.md` | 4-page fictional ML report; pages split on `---` lines, numbered from 1 | — |
| `project.json` | key `project`: 1 project, P01 | `Project` |
| `members.json` | key `members`: M01–M04, all consents true | `Member` |
| `decisions.json` | key `decisions`: D01–D05, all `verified` | `DecisionCard` |

Every JSON file has a top-level `"_note": "SYNTHETIC DEMO DATA ..."`. Load the list under its key:

```python
import json
from busfactor.models import DecisionCard
raw = json.load(open("data/demo/decisions.json"))
decisions = [DecisionCard.model_validate(d) for d in raw["decisions"]]
```

Every `source_refs[].quote` in `decisions.json` is an exact substring of the cited page of `project_report.md`.

Later we replace the content with our real project's 5 decisions but **keep the IDs** (P01, D01–D05, M01–M04).
