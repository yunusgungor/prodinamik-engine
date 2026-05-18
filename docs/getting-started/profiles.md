# Built-in Profiles

Prodinamik Engine ships with 4 production-ready profiles.

| Profile | States | Transitions | Validators | Use Case |
|---------|--------|-------------|------------|----------|
| **content** | 9 | 11 | SlopScan, Length, Schema | Blog/newsletter pipeline |
| **software** | 7 | 10 | Spec, Build, Test, Lint | dev-cycle, open-source |
| **research** | 10 | 15 | Scope, Citation, Method, Stats | Academic papers |
| **design** | 8 | 13 | Brief, Research, A11Y, DS, RWD, IX | UI/UX workflow |

## Creating a Custom Profile

```python
from engine.profile import ProductProfile, Budget, ValidatorDef, ValidatorTier

SM_YAML = """
profile: hardware
name: hardware-workflow
version: 1.0
states:
  spec:
    type: initial
    max_reentries: 1
    timeout: 3600
  layout:
    type: intermediate
    max_reentries: 5
  fabrication:
    type: intermediate
    max_reentries: 3
  testing:
    type: intermediate
    max_reentries: 10
  release:
    type: terminal
    max_reentries: 0
  cancelled:
    type: terminal
    max_reentries: 0
transitions:
  spec -> layout: {type: REVERSIBLE}
  layout -> fabrication: {type: IRREVERSIBLE}
  fabrication -> testing: {type: REVERSIBLE}
  testing -> release: {type: COMPENSABLE, condition: "human_approved"}
  testing -> layout: {type: REVERSIBLE, condition: "changes_requested"}
  layout -> cancelled: {type: REVERSIBLE}
"""

class HardwareProfile(ProductProfile):
    name = "hardware"
    version = "1.0"
    description = "Hardware design workflow"
    state_machine_yaml = SM_YAML

    @property
    def validators(self):
        return [
            ValidatorDef(name="SpecCheck", tier=ValidatorTier.T1),
            ValidatorDef(name="DRCCheck", tier=ValidatorTier.T1),
        ]

    @property
    def adapters(self):
        return []

    @property
    def budget(self):
        return Budget(soft_limit_usd=50, hard_limit_usd=100)
```

Save as `profiles/hardware.py` and validate:

```bash
prodinamik validate profiles/hardware.py
prodinamik run hardware "RISC-V core"
```
