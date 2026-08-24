# Migration and audit history

This directory preserves completed migration and audit evidence. It is
non-normative and does not define the current product contract. Establish the
present behavior from the [user documentation](../../docs/index.md), the
[current architecture](../architecture/overview.md), and accepted or
superseding [ADRs](../adr/README.md) before consulting a historical record.

Statements in the record pages apply to their named phase or audit. Several
representative surfaces have since changed:

- historical `panel-solvers` project wording is superseded by the current
  `panelsolver` identity;
- historical `--flush-every-cases` is superseded by the current
  `--checkpoint-every-cases` option described in the
  [CLI guide](../../docs/user-guide/cli.md);
- `.xls` is not a current supported input format;
- NPZ is not a current output format;
- legacy direct-Python modules are not part of the current public
  [Python API](../../docs/reference/python-api.md).

Do not rewrite the record pages to match current behavior. Their hashes,
goldens, tolerances, source commits, observed differences, execution records,
and audit results remain evidence for regression and compatibility work.

## Migration

- [Migration plan](migration/MIGRATION_PLAN.md)
- [Pinned migration sources](migration/MIGRATION_SOURCES.md)
- [Phase 1 inventory and goldens](migration/phase1/BEHAVIORAL_INVENTORY.md)
- [Phase 1 golden baselines](migration/phase1/GOLDEN_BASELINES.md)
- [Phase 1 legacy differences](migration/phase1/LEGACY_DIFFERENCES.md)
- [Phase 1 tolerances](migration/phase1/TOLERANCES.md)
- [Phase 3 adapters](migration/PHASE3_ADAPTERS.md)
- [Phase 4 models](migration/PHASE4_MODELS.md)
- [Phase 5 execution](migration/PHASE5_EXECUTION.md)
- [Phase 6 GUI](migration/PHASE6_GUI.md)
- [Phase 7 compatibility](migration/PHASE7_COMPATIBILITY.md)
- [Phase 7 user/release handoff](migration/PHASE7_USER_GUIDE.md)

## Audits

- [Phase 7 execution record](audits/PHASE7_EXECUTION_RECORD.md)
- [Phase 8 execution record](audits/PHASE8_EXECUTION_RECORD.md)
- [Phase 8 final audit](audits/PHASE8_FINAL_AUDIT.md)
- [Phase 8 issue disposition](audits/PHASE8_ISSUE_DISPOSITION.md)
