import "/src/style.scss";
import * as bootstrap from "bootstrap";
import cronValidate from "cron-validate";

const API_BASE = "http://192.168.0.15:8000/api";

// Initialize modals with focus options
const modals = {
  add: new bootstrap.Modal(document.getElementById("addModal"), {
    focus: false,
  }),
  edit: new bootstrap.Modal(document.getElementById("editModal"), {
    focus: false,
  }),
  delete: new bootstrap.Modal(document.getElementById("deleteModal"), {
    focus: false,
  }),
};

// Add modal hide event listeners
["addModal", "editModal", "deleteModal"].forEach((modalId) => {
  document.getElementById(modalId).addEventListener("hidden.bs.modal", () => {
    document.querySelector("[data-refresh]").focus();
  });
});

async function loadHostname() {
  try {
    const res = await fetch(`${API_BASE}/hostname`);
    const data = await res.json();
    console.log(data);
    const hostnameElement = document.getElementById("hostname");
    if (data.hostname) {
      hostnameElement.textContent = `Hostname: ${data.hostname}`;
    } else {
      hostnameElement.textContent = "Hostname: Not available";
    }
  } catch (error) {
    console.error("Error fetching hostname:", error);
    const hostnameElement = document.getElementById("hostname");
    hostnameElement.textContent = "Hostname: Error fetching";
  }
}
loadHostname();

async function loadHealthStatus() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    console.log(data);
    const healthStatusElement = document.getElementById("healthStatus");
    const healthIndicator = document.querySelector(".health-indicator");
    if (data.status === "ok") {
      healthStatusElement.textContent = "Running";
      healthIndicator.className = "health-indicator bg-success";
    } else if (data.status === "unhealthy") {
      healthStatusElement.textContent = "Unhealthy";
      healthIndicator.className = "health-indicator bg-danger";
    } else {
      healthStatusElement.textContent = "Unknown";
      healthIndicator.className = "health-indicator bg-warning";
    }
  } catch (error) {
    console.error("Error fetching health status:", error);
    const healthStatusElement = document.getElementById("healthStatus");
    const healthIndicator = document.querySelector(".health-indicator");
    healthStatusElement.textContent = "Error fetching";
    healthIndicator.className = "health-indicator bg-secondary";
  }
}
loadHealthStatus();

async function loadJobs() {
  const res = await fetch(`${API_BASE}/cron-jobs`);
  const jobs = await res.json();

  console.log(jobs);
  countJobsByStatus(jobs);
  const tbody = document.getElementById("cronTableBody");
  tbody.innerHTML = "";
  jobs.forEach((job, index) => {
    const row = `<tr>
        <td class="text-nowrap">${job.schedule}</td>
        <td>${job.command}</td>
        <td>
          <span class="badge ${job.enabled ? "badge-success" : "badge-danger"}">
            ${job.enabled ? "Active" : "Inactive"}
          </span>
        </td>
        <td>
          <div class="dropdown">
            <button class="btn btn-sm btn-dark" type="button" data-bs-toggle="dropdown" aria-expanded="false">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3C11.175 3 10.5 3.675 10.5 4.5C10.5 5.325 11.175 6 12 6C12.825 6 13.5 5.325 13.5 4.5C13.5 3.675 12.825 3 12 3ZM12 18C11.175 18 10.5 18.675 10.5 19.5C10.5 20.325 11.175 21 12 21C12.825 21 13.5 20.325 13.5 19.5C13.5 18.675 12.825 18 12 18ZM12 10.5C11.175 10.5 10.5 11.175 10.5 12C10.5 12.825 11.175 13.5 12 13.5C12.825 13.5 13.5 12.825 13.5 12C13.5 11.175 12.825 10.5 12 10.5Z"></path></svg>
            </button>
            <ul class="dropdown-menu">
            <li><a class="dropdown-item d-flex align-items-center gap-2" href="#" onclick="loadLogs('${job.log_path}')">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 22H5C3.34315 22 2 20.6569 2 19V3C2 2.44772 2.44772 2 3 2H17C17.5523 2 18 2.44772 18 3V15H22V19C22 20.6569 20.6569 22 19 22ZM18 17V19C18 19.5523 18.4477 20 19 20C19.5523 20 20 19.5523 20 19V17H18ZM16 20V4H4V19C4 19.5523 4.44772 20 5 20H16ZM6 7H14V9H6V7ZM6 11H14V13H6V11ZM6 15H11V17H6V15Z"></path></svg>
            View logs</a></li>
            <li>
                <a class="dropdown-item d-flex align-items-center gap-2" href="#" data-action="duplicate" data-index="${index}">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6.9998 6V3C6.9998 2.44772 7.44752 2 7.9998 2H19.9998C20.5521 2 20.9998 2.44772 20.9998 3V17C20.9998 17.5523 20.5521 18 19.9998 18H16.9998V20.9991C16.9998 21.5519 16.5499 22 15.993 22H4.00666C3.45059 22 3 21.5554 3 20.9991L3.0026 7.00087C3.0027 6.44811 3.45264 6 4.00942 6H6.9998ZM5.00242 8L5.00019 20H14.9998V8H5.00242ZM8.9998 6H16.9998V16H18.9998V4H8.9998V6Z"></path></svg>
                Duplicate
                </a>
              </li>
              <li><a class="dropdown-item d-flex align-items-center gap-2" href="#" data-action="edit" data-index="${index}" data-schedule="${job.schedule}" data-command="${job.command}" data-enabled="${job.enabled}" data-has-logging="${job.has_logging}">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6.41421 15.89L16.5563 5.74785L15.1421 4.33363L5 14.4758V15.89H6.41421ZM7.24264 17.89H3V13.6473L14.435 2.21231C14.8256 1.82179 15.4587 1.82179 15.8492 2.21231L18.6777 5.04074C19.0682 5.43126 19.0682 6.06443 18.6777 6.45495L7.24264 17.89ZM3 19.89H21V21.89H3V19.89Z"></path></svg>
              Edit</a></li>
              <li><a class="dropdown-item text-danger d-flex align-items-center gap-2" href="#" data-action="delete" data-index="${index}">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4V2H17V4H22V6H20V21C20 21.5523 19.5523 22 19 22H5C4.44772 22 4 21.5523 4 21V6H2V4H7ZM6 6V20H18V6H6ZM9 9H11V17H9V9ZM13 9H15V17H13V9Z"></path></svg>
              Delete</a></li>
            </ul>
          </div>
        </td>
      </tr>`;
    tbody.insertAdjacentHTML("beforeend", row);
  });

  function countJobsByStatus(jobs) {
    // Update total jobs count
    const totalJobsElement = document.getElementById("totalJobs");
    totalJobsElement.textContent = jobs.length > 0 ? `${jobs.length}` : "0";

    // Update active jobs count
    const activeJobsElement = document.getElementById("activeJobs");
    activeJobsElement.textContent = jobs.filter((job) => job.enabled).length > 0 ? `${jobs.filter((job) => job.enabled).length}` : "0";

    // Update inactive jobs count
    const inactiveJobsElement = document.getElementById("inactiveJobs");
    inactiveJobsElement.textContent = jobs.filter((job) => !job.enabled).length > 0 ? `${jobs.filter((job) => !job.enabled).length}` : "0";
  }

  // Add event listeners using delegation
  document.getElementById("cronTableBody").addEventListener("click", async (e) => {
    const target = e.target.closest("[data-action]");
    if (!target) return;
    const action = target.getAttribute("data-action");
    const index = target.getAttribute("data-index");
    if (action === "duplicate") {
      await duplicateJob(index);
      loadJobs();
    } else if (action === "delete") {
      e.preventDefault();
      deleteJob(parseInt(index));
    } else if (action === "edit") {
      e.preventDefault();
      editJob(parseInt(index), target.dataset.schedule, target.dataset.command, target.dataset.enabled === "true", target.dataset.hasLogging === "true");
    }
  });
}

let jobToDelete = null;

async function deleteJob(index) {
  jobToDelete = index;
  modals.delete.show();
}

// Add confirm delete handler
document.getElementById("confirmDelete").addEventListener("click", async () => {
  if (jobToDelete !== null) {
    await fetch(`${API_BASE}/cron-jobs/${jobToDelete}`, { method: "DELETE" });
    document.querySelector("[data-refresh]").focus();
    modals.delete.hide(); // Changed from deleteModal.hide()
    jobToDelete = null;
    loadJobs();
  }
});
document.getElementById("addForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;

  // Validate cron schedule
  const cronResult = cronValidate(form.schedule.value);
  if (!cronResult.isValid()) {
    alert("Invalid cron schedule!");
    form.schedule.focus();
    return;
  }

  let command = form.command.value;
  const hasLogging = form.has_logging?.checked || false;
  if (hasLogging && !command.trim().endsWith("2>&1")) {
    command = command.trim() + " 2>&1";
  }

  const payload = {
    schedule: form.schedule.value,
    command,
    enabled: form.enabled.checked,
    comment: form.comment?.value || "",
    valid: cronResult.isValid(),
    has_logging: hasLogging,
  };

  await fetch(`${API_BASE}/cron-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  document.querySelector("[data-refresh]").focus();
  modals.add.hide();
  form.reset();
  loadJobs();
});

// Modify the editJob function to include enabled state
window.editJob = function (index, schedule, command, enabled, hasLogging) {
  const form = document.getElementById("editForm");
  form.index.value = index;
  form.schedule.value = schedule;
  form.command.value = command;
  form.enabled.checked = enabled;
  form.has_logging.checked = hasLogging;
  modals.edit.show();
};

// Update the edit form submit handler
document.getElementById("editForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;

  // Validate cron schedule
  const cronResult = cronValidate(form.schedule.value);
  if (!cronResult.isValid()) {
    alert("Invalid cron schedule!");
    form.schedule.focus();
    return;
  }

  let command = form.command.value.trim();
  const hasLogging = form.has_logging?.checked || false;
  if (hasLogging && !command.endsWith("2>&1")) {
    command = command + " 2>&1";
  } else if (!hasLogging && command.endsWith("2>&1")) {
    command = command.replace(/\s*2>&1$/, "");
  }

  const payload = {
    index: parseInt(form.index.value),
    schedule: form.schedule.value,
    command,
    enabled: form.enabled.checked,
    comment: form.comment?.value || "",
    valid: cronResult.isValid(),
    has_logging: hasLogging,
  };

  await fetch(`${API_BASE}/cron-jobs`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  document.querySelector("[data-refresh]").focus();
  modals.edit.hide();
  form.reset();
  loadJobs();
});

// Add event listener for refresh button
document.querySelector("[data-refresh]").addEventListener("click", loadJobs);

// Initial load
loadJobs();

async function loadLogs(logPath, lines = 100) {
  if (!logPath) {
    document.getElementById("logOutput").textContent = "No log file specified.";
    const logModal = new bootstrap.Modal(document.getElementById("logModal"));
    logModal.show();
    return;
  }
  const res = await fetch(`${API_BASE}/cron-jobs/logs?path=${encodeURIComponent(logPath)}&lines=${lines}`);
  const data = await res.json();
  const logElement = document.getElementById("logOutput");
  if (data.log) {
    logElement.textContent = data.log;
  } else {
    logElement.textContent = data.error || "No log data available.";
  }
  // Show the modal after loading the log
  const logModal = new bootstrap.Modal(document.getElementById("logModal"));
  logModal.show();
}

// Make loadLogs available globally
window.loadLogs = loadLogs;

async function duplicateJob(index) {
  await fetch(`${API_BASE}/cron-jobs/${index}/duplicate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}
