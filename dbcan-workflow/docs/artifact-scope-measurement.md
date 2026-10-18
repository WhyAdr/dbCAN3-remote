# Operation-scoped artifact acceptance

Measured with the zero-hit fixture, `summarize --sample-id sample`, on an isolated
5ec0414 source copy and the C6 working implementation. Sizes include pretty JSON.

| Unrelated files in metadata | Before bytes / entries | After bytes / entries |
|---|---|---|
| 0 | 4529 / 8 | 5699 / 8 |
| 500 | 78029 / 508 | 5707 / 8 |
| 5000 | 739529 / 5008 | 5707 / 8 |

The 8-byte first/repeat difference comes from artifact status: created versus
modified. Normalizing status and self-hashes yields exactly flat size. The run
index test seeds 5000 native files and confirms none are directory-inventoried;
production native bytes remain inventoried via the observed-manifest pointer.

Test-first C6 probes both reproduced their named defects before the fix. One
concurrent probe process also saw the schema update mid-run; the complete gate
was rerun against the finished source and passed without concurrent edits.
