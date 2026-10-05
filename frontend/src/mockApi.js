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
