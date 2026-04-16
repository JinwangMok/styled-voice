# styled-voice operations playbook

## Scope

This document covers the operational boundary around `/styled-voice`:

- direct VoxCPM backend health
- nginx/front-door 502 triage
- `vllm` + `voxcpm` coexistence checks
- restart / memory-pressure playbook

It is intentionally separate from the external-skill contract. The skill should keep using the direct backend even if nginx/front-door is unhealthy.

## Core principles

1. **Keep the skill contract simple.** `/styled-voice` should target the direct endpoint first.
2. **Treat nginx 502 as an infrastructure issue.** Do not block skill development on front-door health.
3. **Assume GPU/memory contention is real.** `vllm` and `voxcpm` may interfere under pressure.
4. **Validate the backend hop-by-hop.** Do not jump straight from “Discord failed” to “VoxCPM is broken.”

## Known topology

- direct styled-voice backend: `http://10.40.40.40:9100/v1/audio/speech`
- nginx/front-door route: previously unhealthy; investigate separately
- cluster automation repo of interest: `dgx-spark-ai-cluster`
- setup entrypoint likely to matter for nginx remediation: `setup-single.sh`

## Quick triage order

When `/styled-voice` fails, check in this order:

### 1) direct backend reachable?

```bash
curl -sv http://10.40.40.40:9100/health
curl -sv http://10.40.40.40:9100/v1/audio/speech
```

If the host/port is dead, do not waste time on nginx first.

### 2) process/port ownership

```bash
ss -ltnp | grep -E ':9100|:80|:443'
ps -ef | grep -E 'voxcpm|vllm|nginx' | grep -v grep
```

Questions:

- is VoxCPM actually listening on 9100?
- is nginx running?
- are there duplicate processes or stale processes?
- did setup restart one service but not the other?

### 3) resource pressure

```bash
nvidia-smi
free -h
ps -eo pid,ppid,%mem,%cpu,cmd --sort=-%mem | head -20
journalctl -u nginx -n 100 --no-pager
```

Questions:

- did GPU memory exhaustion kill or destabilize a service?
- did system RAM pressure cause OOM or swap thrash?
- do nginx logs show upstream timeout / connection refused / bad gateway?

### 4) nginx upstream mapping

Check the effective nginx config:

```bash
sudo nginx -t
sudo nginx -T | sed -n '/upstream/,/}/p'
sudo nginx -T | sed -n '/server_name/,/}/p'
```

Verify:

- correct upstream host/port for VoxCPM
- any stale hostname/IP from old deployments
- timeout/body-size settings large enough for audio uploads
- whether the `/tts/...` route and direct VoxCPM route disagree

### 5) app-level backend validation

If nginx is healthy but requests still fail:

- send a minimal curl directly to VoxCPM
- inspect returned headers/body
- confirm it returns actual audio payloads, not HTML/JSON errors
- compare behavior with and without normalized WAV inputs

## Minimal startup playbook

Suggested order after reboot or restart:

1. start the service that owns the VoxCPM backend
2. verify direct `:9100` health locally
3. start/refresh nginx only after the upstream is confirmed healthy
4. test a tiny direct synthesis request
5. test the front-door route separately
6. only then test Discord end-to-end

This prevents blaming Discord/Hermes when the upstream is not actually serving.

## Memory-pressure playbook

If `vllm` and `voxcpm` coexistence becomes unstable:

1. capture current state before restarting anything
   ```bash
   nvidia-smi
   free -h
   ps -ef | grep -E 'voxcpm|vllm' | grep -v grep
   ```
2. identify which process owns most GPU memory / RAM
3. restart only the failed service first
4. if repeated failures occur, reduce concurrency or stagger startup order
5. document whether failure mode is:
   - port not listening
   - upstream timeout
   - connection refused
   - OOM / process exit
   - bad gateway with healthy upstream process

## Symptoms → likely causes

### nginx returns 502 immediately
Likely causes:
- upstream port not listening
- nginx upstream target wrong
- service crashed or never finished startup
- local firewall / bind-address mismatch

### direct `:9100` works but nginx 502s
Likely causes:
- stale nginx upstream config
- nginx route pointing to wrong host/container name
- proxy timeout/body-size/header buffering issue
- nginx not reloaded after config change

### both direct and nginx fail under load
Likely causes:
- VoxCPM process unstable
- GPU/RAM contention with `vllm`
- backend worker crash on malformed audio
- systemic node pressure

### only some Discord uploads fail
Likely causes:
- Discord cache media/container mismatch
- backend decoder failure on raw cached file
- missing normalize-and-retry flow

## Verification checklist after changes

- [ ] direct `:9100` health confirmed
- [ ] direct synthesis request returns valid audio
- [ ] nginx config test passes (`nginx -t`)
- [ ] nginx route proxies successfully
- [ ] `vllm` and `voxcpm` both stay up after restart
- [ ] no immediate OOM / GPU eviction signs
- [ ] Discord `/styled-voice` still works with normalized fallback

## Pending follow-up

The actual nginx remediation should be done in the infrastructure repo/path that owns deployment behavior, especially `dgx-spark-ai-cluster` and `setup-single.sh`. This repo should only document the operational playbook and keep the external skill contract clean.
