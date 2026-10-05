# Manifest file status

`database_v5-2-9_5-5-2026.expected.sha256` matches the archive's recorded `metadata/database_sha256sums.txt` byte-for-byte (646 entries; SHA-256 `0f20c1986c32df59723cffc20b677789ed0c12819cd0939e16788f58dea406d2`). The database directory itself is absent, so this is a preserved final observed manifest used as the comparison baseline, not a newly observed cache.

`requirements-observed.lock` matches the archived `metadata/pip-freeze.txt` byte-for-byte (SHA-256 `19b39109afc22c23f2edbb9543e0299d16ee41333cc4bcdf2860e7827170f6eb`). It pins package versions but contains no artifact hashes.

`diamond-linux64-v2.2.8.expected.sha256` records the archive digest embedded in the archived setup script. The binary archive was not present to re-hash in this recovery.
