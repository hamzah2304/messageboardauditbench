# Native bridge permissions and usage accounting

The native Inspect task uses an `isolated-docker` environment. It keeps Docker
networking disabled, drops all Linux capabilities, enables no-new-privileges,
and executes the bridge and agent as uid 1000. Declining root execution makes
Inspect select its unprivileged injection path, avoiding the model proxy's
permission failure when it writes an agent-owned request directory.

The adapter wraps every environment returned by Inspect's Docker factory. It
uses private Docker implementation fields, so dependency upgrades need a
container smoke test as well as the factory and execution-policy unit tests.
The bridge shares the agent's uid; this does not isolate the bridge's files
from agent commands. Helpers must remain free of answers and credentials.

Subscription execution retains its existing network policy. Moving subscription
credentials and model connections outside the tool container is separate work.

Usage schema 3 distinguishes unavailable reasoning counts from reported zero,
labels CLI estimates, and leaves partially reported totals unknown. Codex token
snapshots are combined across sessions without counting copied snapshots twice.
Retry transcript counts and hook feedback are included when their files exist.
This does not add complete reasoning-text capture, retry capture, or actual tool
start/end timestamps to every backend. Those remain separate telemetry work.

Validation for this extraction: 133 unit tests passed. A live Docker smoke test
could not be repeated in this session because access to the Colima Docker socket
was denied. The source worktree records successful offline Claude and Codex mock
smokes, but those do not independently validate this extracted branch.
