import cronstrue from "cronstrue";

const frequency = document.getElementById("frequency");
const hour = document.getElementById("hour");
const minute = document.getElementById("minute");
const dayOfWeek = document.getElementById("dayOfWeek");
const dayOfMonth = document.getElementById("dayOfMonth");

const cronStringEl = document.getElementById("cronString");
const addJobSchedule = document.getElementById("addJobSchedule");
const cronTextEl = document.getElementById("cronText");

// Fill dropdowns
for (let i = 0; i < 24; i++) {
  hour.innerHTML += `<option value="${i}">${String(i).padStart(2, "0")}h</option>`;
}
for (let i = 0; i < 60; i++) {
  minute.innerHTML += `<option value="${i}">${String(i).padStart(2, "0")}m</option>`;
}
for (let i = 1; i <= 31; i++) {
  dayOfMonth.innerHTML += `<option value="${i}">${i}</option>`;
}

function buildCron() {
  let cron = "* * * * *";
  switch (frequency.value) {
    case "minute":
      cron = "* * * * *";
      break;
    case "hourly":
      cron = `${minute.value} * * * *`;
      break;
    case "daily":
      cron = `${minute.value} ${hour.value} * * *`;
      break;
    case "weekly":
      cron = `${minute.value} ${hour.value} * * ${dayOfWeek.value}`;
      break;
    case "monthly":
      cron = `${minute.value} ${hour.value} ${dayOfMonth.value} * *`;
      break;
    case "custom":
      cron = [document.getElementById("cMinute").value || "*", document.getElementById("cHour").value || "*", document.getElementById("cDayOfMonth").value || "*", document.getElementById("cMonth").value || "*", document.getElementById("cDayOfWeek").value || "*"].join(" ");
      break;
  }
  cronStringEl.textContent = cron;
  addJobSchedule.value = cron;
  try {
    cronTextEl.textContent = cronstrue.toString(cron);
  } catch {
    cronTextEl.textContent = "Invalid cron expression";
  }
}

function toggleSections() {
  document.getElementById("timeSelectors").style.display = frequency.value === "daily" || frequency.value === "weekly" || frequency.value === "monthly" ? "block" : "none";
  document.getElementById("weeklySelector").style.display = frequency.value === "weekly" ? "block" : "none";
  document.getElementById("monthlySelector").style.display = frequency.value === "monthly" ? "block" : "none";
  document.getElementById("customSelector").style.display = frequency.value === "custom" ? "block" : "none";
  buildCron();
}

// Event listeners
document.querySelectorAll("select, input").forEach((el) => el.addEventListener("change", buildCron));
frequency.addEventListener("change", toggleSections);

// Init
buildCron();
