# Independent startup-artifact / COW recovery review

Source `54e3768bc1869f9cb8e81321a92030a0e44ccfdb`, proof-only HEAD
`047e633c0ad960857b8910abefa7fd7fc3280320` in clean rem25-bootstrap-recovery.
Launcher SHA256 `8df642a59cceb63cc8c7fea5ba4d8990bef85469ddd59dd10d3df1172482db44`.

**145 PASS in4.08s**, receipt `startup-after-v2.xml`:129 author tests plus16
independent tests (the7 previous recovery assertions plus9 startup-boundary
cases). No remaining reproduced P0/P1 in this narrow offline boundary review.
Initial default-sandbox attempt could not create its dedicated temp directory
(WinError5); no product conclusion is drawn. Scoped retry occurred only after
the author's proof commit/tool phase had closed. No escalation/tool remains active.

## Provenance and exact admission

Trusted startup `_arecover_projects` calls `arecover_publication`, which uses
`docker_deploy.inspect_deployment` → `PublicationRegistry(...).status(project)`.
The registry constructor creates `empty-runtime-stage`; missing-journal status
uses file_lock, which initializes an empty exact project lock with byte0x30
(`b'0'`). An unregistered publication returns before Docker resource calls.
This explains the native v1 failure without turning these files into product
code or evidence of a deployment.

Initial recovery_snapshot remains unchanged, strict12 original files. Default
verify_recovery_invariants after_startup=False also rejects the startup pair.
Only post-readiness recovery calls pass after_startup=True. Their allowance is
exact `.autospec-supervisor/<same project>/publication/<same project>.lock`
with one byteb'0', plus exact `publication/empty-runtime-stage` as an empty
directory. Original state/oracle/monitor/source/journal hashes and file checks
remain in force; this is not a wildcard publication directory exemption.

Independent tests show exact pair can proceed through only one mocked same-ID
resume; an initial pair before recovery admission fails. Wrong lock contents
(including `b'0\n'`), foreign locks, publication JSON journal, an empty child
directory inside the stage, stage product file, extra empty directory and
hardlink all refuse before PUT. Author tests additionally exercise exact trusted
Registry.status provenance without Docker, wrong project/path/type/size and
symlink/junction aliases. The earlier async-disk/RPC contradiction/monitor-history
regressions are still in this green corpus, not dropped.

## Native helper and historical v1

The inspected helper clones only validated incident metadata into a fresh owned
fixture, verifies every copied hash and isolates WORKSPACE_ROOT to that copy.
Real transport permits only exact health/project GET and languagePUTpython.
Exact `/resume-build` POST is intercepted before actual_http; synthetic ACK
creates only an owned stop intent. No second project creation or provider start
is called, and no product source is copied/executed. Original campaign snapshot
and original runtime files are rechecked after the probe.

Native v1 receipt is preserved, SHA256
`a5d79742a8107dad3986f8968965de95b57f76592b3ce7d09b87b2292ec770c9`.
It records AdmissionError before PUT, only health/projectGETs, zero transmitted
POSTs/cost/agent calls, closed retained handle/direct child exit0 and original
campaign/runtime intact. Immediate port_closed=false is retained, not relabeled
PASS; parent subsequently observed no listener. v1's resume_ack_synthetic=true
describes its configured interception, not an actually reached POST.

Current helper SHA256
`e76cd90ed9afaf60073f2e30d284e20d7df7a29ed538159056723b3d8028b734`
now derives intercepted count/ACK from requests and performs a bounded5s
read-only port-close observation. None of the success/count/zero-cost/original
integrity assertions is removed. Native v2 is still a separate parent-run
condition at report time; these145 offline passes do not claim its result.

This reviewer did not run the native helper, actual API, factory startup,
provider/auth/preflight/Docker or generation, and did not write any actual
campaign or parent/author implementation file. Only trusted supervisor tests,
synthetic owned temp incidents, file-lock fixtures and inert process/HTTP doubles
executed. Root alone owns integration, native COW retry, fresh admission and any
single actual same-project continuation. No launch/product PASS is inferred.
