"""Capture the full finished run before workspace transport can merge snapshots."""
import sys,io,contextlib,json,tarfile,hashlib
from pathlib import Path
base=Path('/workspace/scratch/51b8ca04e32d');sys.path.insert(0,str(base/'dbCAN3-remote/dbcan-workflow/scripts'))
import dbcan_cli as cli
root=base/'c14-run';out,err=io.StringIO(),io.StringIO()
args=['run','--input-dir',str(root/'inputs'),'--results-dir',str(root/'results-atomic'),'--metadata-dir',str(root/'metadata-atomic'),
 '--db-dir','/tmp/dbcan-c14-database','--expected-manifest',str(base/'dbCAN3-remote/dbcan-workflow/environment/database_v5-2-9_5-5-2026.expected.sha256'),
 '--env-dir',str(base/'c14-runtime/env'),'--samples','C14-NMZ','--threads','4','--profile','sandbox']
with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=cli.main(args)
(root/'run-envelope-atomic.json').write_text(out.getvalue());(root/'run-stderr-atomic.log').write_text(err.getvalue())
env=json.loads(out.getvalue());mismatches=[]
for a in env['artifacts']:
 if a['written'] and a['sha256'] is not None:
  path=Path(a['path']);actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
  if actual!=a['sha256']:mismatches.append({'role':a['role'],'path':a['path'],'expected':a['sha256'],'actual':actual})
report={'exit_code':code,'outcome':env['outcome'],'evidence':env['evidence'],'artifact_hash_mismatches':mismatches}
(root/'atomic-verification.json').write_text(json.dumps(report,indent=2)+'\n')
with tarfile.open(root/'C14-completed-atomic.tar.gz','w:gz') as archive:
 for name in ['inputs','results-atomic','metadata-atomic','run-envelope-atomic.json','run-stderr-atomic.log','atomic-verification.json','provisioning']:
  archive.add(root/name,arcname=name)
print(json.dumps(report));print('archive_sha256',hashlib.sha256((root/'C14-completed-atomic.tar.gz').read_bytes()).hexdigest())
assert code==0 and not mismatches,report
