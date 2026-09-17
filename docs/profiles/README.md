# Makoto reference profiles

`origin-l3-reference-v1.schema.json` is the standard Makoto v0.2 reference profile for
policy-controlled capture. Applied to an origin predicate, it requires a source record or device
identifier, an ingestion timestamp, a run identifier, a non-null approver, and a freshness SLO.

The profile is an example control set, not a universal core schema. Producers pin its exact root
and closure digests in the ordinary Makoto profile reference, and receivers list that reference in
the trusted Origin L3 assessor rule. Organizations may use a stricter private profile instead.
