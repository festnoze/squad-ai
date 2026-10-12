// Legacy entrypoint intentionally refuses: Chromium rendering must occur only
// through the supervisor's exact RuntimeSession + DockerBrowserSession NETNONE.
// A host Node driver is not an OS boundary for generated browser JavaScript.
'use strict';
console.error('ISOLATION_UNAVAILABLE: legacy host browser driver disabled; use owned DockerBrowserSession');
process.exitCode = 2;
