"use strict";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTimestamp(ts) {
  if (!ts) return "\u2014";
  var date = new Date(ts.endsWith("Z") ? ts : ts + "Z");
  var now = new Date();
  var diffMs = now - date;
  var diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return diffSec + "s ago";
  var diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return diffMin + "m ago";
  var diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return diffHr + "h ago";
  return date.toLocaleDateString();
}

function scoreClass(score) {
  if (score >= 80) return "score-high";
  if (score >= 60) return "score-mid";
  return "score-low";
}

function scoreGrade(score) {
  if (score >= 95) return "A+";
  if (score >= 90) return "A";
  if (score >= 85) return "B+";
  if (score >= 80) return "B";
  if (score >= 70) return "C";
  if (score >= 60) return "D";
  return "F";
}

function esc(str) {
  var d = document.createElement("span");
  d.textContent = String(str);
  return d.innerHTML;
}

// ── Category Cards ────────────────────────────────────────────────────────────

function renderCategoryCard(name, score) {
  var grid = document.getElementById("category-grid");
  if (!grid) return;

  var id = "cat-" + name.replace(/\s+/g, "-");
  var card = document.getElementById(id);

  var grade = scoreGrade(score);
  var cls = scoreClass(score);
  var pct = Math.max(0, Math.min(100, score));

  if (!card) {
    card = document.createElement("div");
    card.className = "category-card";
    card.id = id;
    grid.appendChild(card);
  }

  // Build DOM safely
  var nameDiv = document.createElement("div");
  nameDiv.className = "category-name";
  nameDiv.textContent = name;

  var scoreDiv = document.createElement("div");
  scoreDiv.className = "category-score-num";
  scoreDiv.textContent = score.toFixed(1);

  var gradeDiv = document.createElement("div");
  gradeDiv.className = "category-grade";
  gradeDiv.textContent = grade;

  var barWrap = document.createElement("div");
  barWrap.className = "score-bar";
  var barFill = document.createElement("div");
  barFill.className = "score-bar-fill " + cls;
  barFill.style.width = pct + "%";
  barWrap.appendChild(barFill);

  card.textContent = "";
  card.appendChild(nameDiv);
  card.appendChild(scoreDiv);
  card.appendChild(gradeDiv);
  card.appendChild(barWrap);
}

// ── Score Fetch ───────────────────────────────────────────────────────────────

async function fetchScores() {
  try {
    var resp = await fetch("/api/v1/scores");
    if (!resp.ok) throw new Error("scores fetch failed");
    var data = await resp.json();

    var overallEl = document.getElementById("overall-score");
    var gradeEl = document.getElementById("overall-grade");
    if (overallEl && data.overall_score != null) {
      overallEl.textContent = data.overall_score.toFixed(1);
    }
    if (gradeEl && data.grade) {
      gradeEl.textContent = data.grade;
    }

    var catEl = document.getElementById("active-categories");
    if (catEl && data.categories) {
      catEl.textContent = Object.keys(data.categories).length;
    }

    if (data.categories) {
      var grid = document.getElementById("category-grid");
      if (grid) grid.textContent = "";
      for (var name in data.categories) {
        var info = data.categories[name];
        var score = typeof info === "object" ? info.score : info;
        renderCategoryCard(name, score);
      }
    }
  } catch (e) {
    console.warn("fetchScores error:", e);
  }
}

// ── Events Fetch ──────────────────────────────────────────────────────────────

function buildEventRow(ev) {
  var tr = document.createElement("tr");

  function td(val) {
    var cell = document.createElement("td");
    cell.textContent = val || "\u2014";
    return cell;
  }

  tr.appendChild(td(formatTimestamp(ev.created_at || ev.timestamp)));
  tr.appendChild(td(ev.event_type));
  tr.appendChild(td(ev.agent_name || ev.agent_id));
  tr.appendChild(td(ev.category));

  var sevTd = document.createElement("td");
  var badge = document.createElement("span");
  var sev = (ev.severity || "info").toLowerCase();
  badge.className = "severity-badge severity-" + sev;
  badge.textContent = ev.severity || "info";
  sevTd.appendChild(badge);
  tr.appendChild(sevTd);

  tr.appendChild(td(ev.description));
  return tr;
}

async function fetchEvents() {
  try {
    var resp = await fetch("/api/v1/events?limit=20");
    if (!resp.ok) throw new Error("events fetch failed");
    var data = await resp.json();

    var tbody = document.getElementById("events-tbody");
    if (!tbody) return;

    var events = Array.isArray(data) ? data : (data.events || []);

    var totalEl = document.getElementById("total-events");
    if (totalEl) {
      totalEl.textContent = data.total != null ? data.total : events.length;
    }

    var rateEl = document.getElementById("event-rate");
    if (rateEl && data.event_rate != null) {
      rateEl.textContent = data.event_rate.toFixed(1);
    } else if (rateEl) {
      var cutoff = Date.now() - 86400000;
      var recent = events.filter(function(e) {
        var t = new Date(e.created_at || e.timestamp || 0);
        return t.getTime() > cutoff;
      });
      rateEl.textContent = recent.length;
    }

    tbody.textContent = "";

    if (!events.length) {
      var emptyRow = document.createElement("tr");
      var emptyCell = document.createElement("td");
      emptyCell.colSpan = 6;
      emptyCell.className = "table-empty";
      emptyCell.textContent = "No events recorded yet.";
      emptyRow.appendChild(emptyCell);
      tbody.appendChild(emptyRow);
      return;
    }

    events.forEach(function(ev) {
      tbody.appendChild(buildEventRow(ev));
    });
  } catch (e) {
    console.warn("fetchEvents error:", e);
    var tbody = document.getElementById("events-tbody");
    if (tbody) {
      tbody.textContent = "";
      var errRow = document.createElement("tr");
      var errCell = document.createElement("td");
      errCell.colSpan = 6;
      errCell.className = "table-empty";
      errCell.textContent = "Failed to load events.";
      errRow.appendChild(errCell);
      tbody.appendChild(errRow);
    }
  }
}

// ── Auto-refresh ──────────────────────────────────────────────────────────────

var countdown = 30;

function refresh() {
  fetchScores();
  fetchEvents();
  countdown = 30;
}

function tick() {
  countdown--;
  var el = document.getElementById("refresh-countdown");
  if (el) el.textContent = countdown;
  if (countdown <= 0) refresh();
}

document.addEventListener("DOMContentLoaded", function() {
  fetchScores();
  fetchEvents();
  setInterval(tick, 1000);
});
