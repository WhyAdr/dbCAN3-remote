# Reporting rules

Keep the following values distinct:

- **Overview candidates:** proteins listed in `overview.tsv` from one or more configured methods.
- **Positive method count:** number of populated method result columns, summarized by `#ofTools`.
- **Resolved-family agreement:** one or more nonzero family roots present in at least two method columns.
- **Family-protein association:** one protein counted under one resolved family. A protein with two families contributes twice to association totals.
- **Query-aligned domain instance:** one method-specific HMM or dbCAN-sub hit row with target coordinates; overlapping hits from the two methods are not deduplicated physical domains.
- **DIAMOND reference association:** family token(s) on a homologous CAZy reference; not query-domain evidence by itself.

Report positive method support separately from same-family agreement. The methods share CAZy-derived information and are not independent biochemical experiments. Keep unresolved family labels in candidate evidence while excluding them from resolved-family counts.

Keep raw model and reference labels. A dbCAN-sub `_e<number>` group is a computational grouping and must not be described as a curated CAZy subfamily. Family-root counts can group labels such as `GH13_22` under GH13 while retaining the complete original label in evidence tables.

For substrate results, separate PUL homology, per-protein dbCAN-sub hints, cluster-level substrate scores, and experimentally demonstrated activity. Interpret the members and neighboring annotations; bitscore sums are not probabilities. A missing substrate label is not evidence that a locus lacks carbohydrate metabolism.

For circular replicons, use original GFF3 topology and sequence-region lengths. Preserve a valid origin-crossing CDS as unrolled coordinates. An exact-category CGC overlay is a derived comparison; retain the native membership tables unchanged.
