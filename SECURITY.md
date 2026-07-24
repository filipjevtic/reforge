# Security Policy

## Supported versions

reforge is pre-1.0 and moves quickly. Only the latest commit on `main` is
supported. Please reproduce any issue against `main` before reporting it.

## Reporting a vulnerability

Report privately through GitHub's
[private vulnerability reporting](https://github.com/filipjevtic/reforge/security/advisories/new).
Please don't open a public issue for a security problem.

Include what you'd expect: how to reproduce it, the impact you see, and any fix
you have in mind. We aim to acknowledge a report within seven days.

## Running reforge safely

reforge exists to run code produced by an AI agent, which means it runs untrusted
code by design. The harness limits the blast radius, but you should still treat
every run as untrusted:

- Each task runs in its own container with no network by default, all Linux
  capabilities dropped, `no-new-privileges` set, and CPU, memory, and PID limits
  applied.
- reforge never mounts your Docker socket into a task container.
- The verifier and its tests are injected only after the agent's changes are
  captured, so a task can't be gamed by editing the tests.

Even so, run reforge on a disposable or isolated host, not on a machine that holds
credentials or data you care about. If a task needs network access (for example to
install packages at build time), grant it deliberately with `--network` rather
than leaving it on for every task.
