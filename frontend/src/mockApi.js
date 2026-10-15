const STORAGE_KEY = "cron-web-manager.mock-jobs";

const defaultJobs = [
  {
    schedule: "*/5 * * * *",
    command: "python3 /opt/jobs/sync_metrics.py >> /var/log/sync-metrics.log 2>&1",
    enabled: true,
    comment: "Metrics sync",
  },
  {
    schedule: "15 3 * * 1",
    command: "/usr/local/bin/backup-db.sh >> /var/log/backup-db.log 2>&1",
    enabled: true,
    comment: "Weekly backup",
  },
  {
    schedule: "0 8 * * 1-5",
    command: "node /srv/app/scripts/send-digest.js",
    enabled: false,
    comment: "Digest email",
  },
  {
    schedule: "0 0 1 * *",
    command: "bash /home/deploy/archive-logs.sh >> /var/log/archive-logs.log 2>&1",
    enabled: true,
    comment: "Monthly archive",
  },
];

const minutesAgo = (minutes) => new Date(Date.now() - minutes * 60_000).toISOString();
const mockExecutionEvents = [
  {
    id: 5,
    observed_at: minutesAgo(8),
    event_type: "launch_observed",
    outcome: "unknown",
    username: "deploy",
    process_id: 24831,
    command: "/usr/local/bin/backup-db.sh",
    source_path: "/var/log/syslog",
  },
  {
    id: 4,
    observed_at: minutesAgo(37),
    event_type: "launch_observed",
    outcome: "unknown",
    username: "www-data",
    process_id: 24702,
    command: "node /srv/app/scripts/send-digest.js",
    source_path: "/var/log/syslog",
  },
  {
    id: 3,
    observed_at: minutesAgo(96),
    event_type: "launch_observed",
    outcome: "unknown",
    username: "deploy",
    process_id: 23914,
    command: "python3 /opt/jobs/sync_metrics.py",
    source_path: "/var/log/syslog",
  },
  {
    id: 2,
    observed_at: minutesAgo(180),
    event_type: "launch_observed",
    outcome: "unknown",
    username: "root",
    process_id: 23106,
    command: "bash /home/deploy/archive-logs.sh",
    source_path: "/var/log/syslog",
  },
];

const mockCrontabChanges = [
  {
    id: 4,
    operation: "update",
    summary: "Move weekly database backup to 03:30",
    related_change_id: null,
    started_at: minutesAgo(18),
    completed_at: minutesAgo(18),
    outcome: "succeeded",
    error: null,
    before_exists: true,
    after_exists: true,
    before_sha256: "a".repeat(64),
    after_sha256: "b".repeat(64),
    after_snapshot_source: "operation_result",
    before_text: "15 3 * * 1 /usr/local/bin/backup-db.sh >> /var/log/backup-db.log 2>&1 # Weekly backup\n",
    after_text: "30 3 * * 1 /usr/local/bin/backup-db.sh >> /var/log/backup-db.log 2>&1 # Weekly backup\n",
    diff: "--- before crontab\n+++ after crontab\n@@ -1 +1 @@\n-15 3 * * 1 /usr/local/bin/backup-db.sh >> /var/log/backup-db.log 2>&1 # Weekly backup\n+30 3 * * 1 /usr/local/bin/backup-db.sh >> /var/log/backup-db.log 2>&1 # Weekly backup\n",
    rollback_diff: "--- current crontab\n+++ restore target\n@@ -1 +1 @@\n-30 3 * * 1 /usr/local/bin/backup-db.sh >> /var/log/backup-db.log 2>&1 # Weekly backup\n+15 3 * * 1 /usr/local/bin/backup-db.sh >> /var/log/backup-db.log 2>&1 # Weekly backup\n",
  },
  {
    id: 3,
    operation: "add",
    summary: "Add nightly cache cleanup",
    related_change_id: null,
    started_at: minutesAgo(82),
    completed_at: minutesAgo(82),
    outcome: "succeeded",
    error: null,
    before_exists: true,
    after_exists: true,
    before_sha256: "c".repeat(64),
    after_sha256: "d".repeat(64),
    after_snapshot_source: "operation_result",
    before_text: "*/5 * * * * python3 /opt/jobs/sync_metrics.py >> /var/log/sync-metrics.log 2>&1 # Metrics sync\n",
    after_text: "*/5 * * * * python3 /opt/jobs/sync_metrics.py >> /var/log/sync-metrics.log 2>&1 # Metrics sync\n\n20 2 * * * /usr/local/bin/clear-cache.sh # Nightly cache cleanup\n",
    diff: "--- before crontab\n+++ after crontab\n@@ -1 +1,3 @@\n */5 * * * * python3 /opt/jobs/sync_metrics.py >> /var/log/sync-metrics.log 2>&1 # Metrics sync\n+\n+20 2 * * * /usr/local/bin/clear-cache.sh # Nightly cache cleanup\n",
    rollback_diff: "--- current crontab\n+++ restore target\n@@ -1,3 +1 @@\n */5 * * * * python3 /opt/jobs/sync_metrics.py >> /var/log/sync-metrics.log 2>&1 # Metrics sync\n-\n-20 2 * * * /usr/local/bin/clear-cache.sh # Nightly cache cleanup\n",
  },
  {
    id: 2,
    operation: "delete",
    summary: "Remove obsolete digest job",
    related_change_id: null,
    started_at: minutesAgo(156),
    completed_at: minutesAgo(156),
    outcome: "failed",
    error: "crontab installation returned a non-zero exit status",
    before_exists: true,
    after_exists: true,
    before_sha256: "e".repeat(64),
    after_sha256: "e".repeat(64),
    after_snapshot_source: "operation_result",
    before_text: "0 8 * * 1-5 node /srv/app/scripts/send-digest.js # Digest email\n",
    after_text: "0 8 * * 1-5 node /srv/app/scripts/send-digest.js # Digest email\n",
    diff: "",
    rollback_diff: "",
  },
];

function extractLogPath(command) {
  const patterns = [/(?:>>|>|2>|2>&1|&>)\s*([^\s]+\.log)/, /tee\s+([^\s]+\.log)/];
  for (const pattern of patterns) {
    const match = command.match(pattern);
    if (match) {
      return match[1];
    }
  }
  return "";
}

function normalizeJob(job) {
  const command = job.command || "";
  return {
    schedule: job.schedule,
    command,
    enabled: Boolean(job.enabled),
    comment: job.comment || "",
    valid: true,
    has_logging: />>\s|>\s|2>&1|2>\s/.test(command),
    log_path: extractLogPath(command),
  };
}

function getStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function loadJobs() {
  const storage = getStorage();
  if (!storage) {
    return defaultJobs.map(normalizeJob);
  }

  const storedJobs = storage.getItem(STORAGE_KEY);
  if (!storedJobs) {
    const seededJobs = defaultJobs.map(normalizeJob);
    storage.setItem(STORAGE_KEY, JSON.stringify(seededJobs));
    return seededJobs;
  }

  try {
    return JSON.parse(storedJobs);
  } catch {
    const seededJobs = defaultJobs.map(normalizeJob);
    storage.setItem(STORAGE_KEY, JSON.stringify(seededJobs));
    return seededJobs;
  }
}

function saveJobs(jobs) {
  const storage = getStorage();
  if (storage) {
    storage.setItem(STORAGE_KEY, JSON.stringify(jobs));
  }
}

function buildRawCrontab(jobs) {
  if (jobs.length === 0) {
    return "";
  }

  return jobs
    .map((job) => {
      const line = `${job.schedule} ${job.command}`;
      const withComment = job.comment ? `${line} # ${job.comment}` : line;
      return job.enabled ? withComment : `# ${withComment}`;
    })
    .join("\n");
}

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return data;
    },
  };
}

function textResponse(message, status = 200) {
  return jsonResponse({ detail: message }, status);
}

function publicMockCrontabChange(change, includeDetails = false) {
  const { before_text, after_text, diff, ...item } = change;
  delete item.rollback_diff;
  return includeDetails ? { ...item, before_text, after_text, diff } : item;
}

function parseRequestUrl(input) {
  const rawUrl = typeof input === "string" ? input : input.url;
  return new URL(rawUrl, window.location.origin);
}

function getLogMessage(path, lines) {
  const header = path ? `Mock log stream for ${path}` : "Mock log stream";
  const rows = [header, "----------------------------------------"];

  for (let index = 0; index < lines; index += 1) {
    rows.push(`2026-10-05T08:${String(index).padStart(2, "0")}:00Z job execution sample line ${index + 1}`);
  }

  return rows.join("\n");
}

export async function mockFetch(input, init = {}) {
  const url = parseRequestUrl(input);
  const method = (init.method || "GET").toUpperCase();
  const jobs = loadJobs();
  const path = url.pathname;

  if (path.endsWith("/hostname") && method === "GET") {
    return jsonResponse({ hostname: "mock-cron-host" });
  }

  if (path.endsWith("/health") && method === "GET") {
    return jsonResponse({ status: "ok" });
  }

  if (path.endsWith("/crontab-history") && method === "GET") {
    const limit = Number(url.searchParams.get("limit") || 100);
    const offset = Number(url.searchParams.get("offset") || 0);
    const items = mockCrontabChanges.slice(offset, offset + limit).map((item) => publicMockCrontabChange(item));
    return jsonResponse({ items, limit, offset });
  }

  const rollbackPreviewMatch = path.match(/\/crontab-history\/(\d+)\/rollback-preview$/);
  if (rollbackPreviewMatch && method === "GET") {
    const change = mockCrontabChanges.find((item) => item.id === Number(rollbackPreviewMatch[1]));
    if (!change) return textResponse("Crontab change not found", 404);
    const canRollback = change.outcome === "succeeded" && Boolean(change.rollback_diff);
    return jsonResponse({
      change_id: change.id,
      can_rollback: canRollback,
      stale: false,
      reason: canRollback ? null : "This mock entry does not have a restorable crontab change.",
      expected_current_sha256: "f".repeat(64),
      recorded_after_sha256: change.after_sha256,
      current_exists: change.after_exists,
      target_exists: change.before_exists,
      diff: change.rollback_diff,
    });
  }

  const rollbackMatch = path.match(/\/crontab-history\/(\d+)\/rollback$/);
  if (rollbackMatch && method === "POST") {
    const change = mockCrontabChanges.find((item) => item.id === Number(rollbackMatch[1]));
    if (!change) return textResponse("Crontab change not found", 404);
    if (change.outcome !== "succeeded" || !change.rollback_diff) {
      return textResponse("This mock entry cannot be rolled back", 409);
    }
    const id = Math.max(...mockCrontabChanges.map((item) => item.id)) + 1;
    const timestamp = new Date().toISOString();
    const rollback = {
      ...change,
      id,
      operation: "rollback",
      summary: `Restore crontab to before change #${change.id}`,
      related_change_id: change.id,
      started_at: timestamp,
      completed_at: timestamp,
      outcome: "succeeded",
      error: null,
      before_sha256: change.after_sha256,
      after_sha256: change.before_sha256,
      before_text: change.after_text,
      after_text: change.before_text,
      before_exists: change.after_exists,
      after_exists: change.before_exists,
      diff: change.rollback_diff,
      rollback_diff: change.diff,
    };
    mockCrontabChanges.unshift(rollback);
    return jsonResponse({ status: "rolled_back", change_id: id });
  }

  const crontabChangeMatch = path.match(/\/crontab-history\/(\d+)$/);
  if (crontabChangeMatch && method === "GET") {
    const change = mockCrontabChanges.find((item) => item.id === Number(crontabChangeMatch[1]));
    return change
      ? jsonResponse(publicMockCrontabChange(change, true))
      : textResponse("Crontab change not found", 404);
  }

  if (path.endsWith("/execution-history") && method === "GET") {
    const limit = Number(url.searchParams.get("limit") || 100);
    const offset = Number(url.searchParams.get("offset") || 0);
    return jsonResponse({
      monitoring: {
        enabled: true,
        available: true,
        path: "/var/log/syslog",
        error: null,
      },
      items: mockExecutionEvents.slice(offset, offset + limit),
      limit,
      offset,
      semantics: {
        event_type: "launch_observed",
        outcome: "unknown",
        note: "Mock cron log entries show launches only; completion and success are unknown.",
      },
    });
  }

  if (path.endsWith("/cron-jobs") && method === "GET") {
    return jsonResponse(jobs);
  }

  if (path.endsWith("/cron-jobs") && method === "POST") {
    const payload = normalizeJob(JSON.parse(init.body || "{}"));
    jobs.push(payload);
    saveJobs(jobs);
    return jsonResponse({ status: "added" }, 201);
  }

  if (path.endsWith("/cron-jobs") && method === "PUT") {
    const payload = JSON.parse(init.body || "{}");
    const index = Number(payload.index);
    if (Number.isNaN(index) || !jobs[index]) {
      return textResponse("Invalid index", 404);
    }

    jobs[index] = normalizeJob(payload);
    saveJobs(jobs);
    return jsonResponse({ status: "updated" });
  }

  if (path.endsWith("/cron-jobs/import") && method === "POST") {
    const payload = JSON.parse(init.body || "{}");
    const importedJobs = (payload.jobs || []).map(normalizeJob);
    const mergedJobs = [...jobs, ...importedJobs];
    saveJobs(mergedJobs);
    return jsonResponse({ status: "imported" });
  }

  if (path.endsWith("/cron-jobs/export") && method === "GET") {
    return jsonResponse(jobs);
  }

  if (path.endsWith("/cron-jobs/raw") && method === "GET") {
    return jsonResponse({ crontab: buildRawCrontab(jobs) });
  }

  if (path.endsWith("/cron-jobs/logs") && method === "GET") {
    const lines = Number(url.searchParams.get("lines") || "12");
    const logPath = url.searchParams.get("path") || "";
    return jsonResponse({
      success: true,
      path: logPath,
      lines_requested: lines,
      log: getLogMessage(logPath, Math.max(lines, 1)),
    });
  }

  const duplicateMatch = path.match(/\/cron-jobs\/(\d+)\/duplicate$/);
  if (duplicateMatch && method === "POST") {
    const index = Number(duplicateMatch[1]);
    if (Number.isNaN(index) || !jobs[index]) {
      return textResponse("Invalid index", 404);
    }

    const duplicated = {
      ...jobs[index],
      enabled: false,
      comment: jobs[index].comment ? `${jobs[index].comment} Copy` : "Copy",
    };
    jobs.push(normalizeJob(duplicated));
    saveJobs(jobs);
    return jsonResponse({ status: "duplicated" });
  }

  const deleteMatch = path.match(/\/cron-jobs\/(\d+)$/);
  if (deleteMatch && method === "DELETE") {
    const index = Number(deleteMatch[1]);
    if (Number.isNaN(index) || !jobs[index]) {
      return textResponse("Invalid index", 404);
    }

    jobs.splice(index, 1);
    saveJobs(jobs);
    return jsonResponse({ status: "deleted" });
  }

  return textResponse(`No mock handler for ${method} ${path}`, 404);
}
