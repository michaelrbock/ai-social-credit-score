const svgNS = "http://www.w3.org/2000/svg";

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(svgNS, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
}

function scoreOf(profile) {
  return profile.score;
}

function scoreLabel(score) {
  if (score >= 800) return "Exceptional manners";
  if (score >= 740) return "Very considerate";
  if (score >= 670) return "Considerate";
  if (score >= 580) return "Room to improve";
  return "Proceed politely";
}

function pointOnGauge(degrees, radius = 122) {
  const radians = degrees * Math.PI / 180;
  return [160 + radius * Math.cos(radians), 157 + radius * Math.sin(radians)];
}

function drawGauge(score) {
  const segments = document.getElementById("gauge-segments");
  segments.replaceChildren();
  const colors = ["#e96875", "#f2a45f", "#edcb68", "#9ed6a3", "#3dbb90"];
  for (let index = 0; index < colors.length; index += 1) {
    const start = pointOnGauge(182 + index * 35.5);
    const end = pointOnGauge(182 + index * 35.5 + 31.5);
    const path = svgElement("path", {
      d: `M ${start[0].toFixed(2)} ${start[1].toFixed(2)} A 122 122 0 0 1 ${end[0].toFixed(2)} ${end[1].toFixed(2)}`,
      fill: "none", stroke: colors[index], "stroke-width": 14, "stroke-linecap": "round"
    });
    segments.append(path);
  }
  const fraction = Math.max(0, Math.min(1, (score - 300) / 550));
  document.getElementById("gauge-needle").setAttribute("transform", `rotate(${(-90 + fraction * 180).toFixed(1)} 160 157)`);
  document.getElementById("score-gauge").setAttribute("aria-label", `Score ${score} out of 850, on a scale from 300 to 850`);
}

function drawHistory(profile) {
  const container = document.getElementById("trend-chart");
  const history = profile.history.length ? profile.history : [{score: profile.score, recordedAt: profile.updatedAt}];
  const dateLabel = value => new Intl.DateTimeFormat(undefined, {month: "short", day: "numeric"}).format(new Date(value));
  const svg = svgElement("svg", {viewBox: "0 0 560 180", role: "img", "aria-label": `${profile.username} score history: ${history.map(point => `${dateLabel(point.recordedAt)} ${point.score}`).join(", ")}`});
  const defs = svgElement("defs");
  const gradient = svgElement("linearGradient", {id: "area-gradient", x1: "0", x2: "0", y1: "0", y2: "1"});
  gradient.append(svgElement("stop", {offset: "0%", "stop-color": "#63d5ac", "stop-opacity": ".35"}), svgElement("stop", {offset: "100%", "stop-color": "#63d5ac", "stop-opacity": "0"}));
  defs.append(gradient);
  svg.append(defs);

  const left = 38, right = 545, top = 8, bottom = 142;
  const yFor = value => bottom - (value - 300) / 550 * (bottom - top);
  const xFor = index => left + (history.length === 1 ? .5 : index / (history.length - 1)) * (right - left);
  for (const value of [850, 575, 300]) {
    const y = yFor(value);
    svg.append(svgElement("line", {x1: left, x2: right, y1: y, y2: y, class: "chart-grid"}));
    const label = svgElement("text", {x: 1, y: y + 3, class: "chart-label"});
    label.textContent = value;
    svg.append(label);
  }
  const points = history.map((point, index) => [xFor(index), yFor(point.score)]);
  const line = points.map(([x, y], index) => `${index ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  if (points.length > 1) {
    const area = `${line} L ${points.at(-1)[0]} ${bottom} L ${points[0][0]} ${bottom} Z`;
    svg.append(svgElement("path", {d: area, fill: "url(#area-gradient)"}));
  }
  svg.append(svgElement("path", {d: line, class: "chart-line"}));
  points.forEach(([x, y], index) => {
    const circle = svgElement("circle", {cx: x, cy: y, r: index === points.length - 1 ? 5 : 3.2, class: "chart-dot"});
    const title = svgElement("title");
    title.textContent = `${dateLabel(history[index].recordedAt)}: ${history[index].score}`;
    circle.append(title);
    svg.append(circle);
    if (points.length <= 4 || index === 0 || index === points.length - 1 || index % 2 === 0) {
      const label = svgElement("text", {x, y: 168, "text-anchor": "middle", class: "chart-label"});
      label.textContent = dateLabel(history[index].recordedAt);
      svg.append(label);
    }
  });
  container.replaceChildren(svg);
}

function showProfile(profile, rows) {
  rows.forEach(({profile: rowProfile, row, button}) => {
    const selected = rowProfile.username === profile.username;
    row.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  const score = scoreOf(profile);
  const change = score - (profile.history[0]?.score ?? score);
  document.getElementById("profile-name").textContent = profile.username;
  document.getElementById("profile-score").textContent = score;
  document.getElementById("profile-rating").textContent = scoreLabel(score);
  document.getElementById("profile-change").textContent = `${change >= 0 ? "+" : ""}${change} pts`;
  document.getElementById("profile-prompts").textContent = profile.promptsScored.toLocaleString();
  document.getElementById("profile-updated").textContent = new Intl.DateTimeFormat(undefined, {month: "short", day: "numeric"}).format(new Date(profile.updatedAt));
  drawGauge(score);
  drawHistory(profile);
}

function renderLeaderboard(profiles) {
  const body = document.getElementById("leaderboard-body");
  body.replaceChildren();
  const rows = [];
  profiles.sort((a, b) => scoreOf(b) - scoreOf(a)).forEach((profile, index) => {
    const row = document.createElement("tr");
    const rank = document.createElement("td");
    rank.className = index < 3 ? "rank top" : "rank";
    rank.textContent = String(index + 1).padStart(2, "0");
    const memberCell = document.createElement("td");
    const button = document.createElement("button");
    button.className = "member-button";
    button.type = "button";
    button.textContent = profile.username;
    memberCell.append(button);
    const scoreCell = document.createElement("td");
    scoreCell.className = "score-cell";
    scoreCell.textContent = scoreOf(profile);
    const movementCell = document.createElement("td");
    const movement = document.createElement("span");
    const change = scoreOf(profile) - (profile.history[0]?.score ?? scoreOf(profile));
    movement.className = `movement${change < 0 ? " down" : change === 0 ? " flat" : ""}`;
    movement.textContent = `${change > 0 ? "↗ +" : change < 0 ? "↘ " : "— "}${change === 0 ? "0" : change}`;
    movementCell.append(movement);
    row.append(rank, memberCell, scoreCell, movementCell);
    body.append(row);
    rows.push({profile, row, button});
    button.addEventListener("click", () => {
      showProfile(profile, rows);
      if (window.matchMedia("(max-width: 850px)").matches) {
        document.getElementById("profile-card").scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
          block: "start"
        });
      }
    });
    row.addEventListener("click", event => {
      if (event.target !== button) button.click();
    });
  });
  if (rows.length) showProfile(rows[0].profile, rows);
}

async function loadLeaderboard() {
  try {
    const response = await fetch("/api/leaderboard", {cache: "no-store"});
    if (!response.ok) throw new Error("The leaderboard could not be loaded.");
    const data = await response.json();
    if (!Array.isArray(data.profiles) || data.profiles.some(profile =>
      typeof profile.username !== "string" || !/^[A-Za-z0-9_-]{1,40}$/.test(profile.username) ||
      !Number.isInteger(profile.score) || profile.score < 300 || profile.score > 850 ||
      !Array.isArray(profile.history) || profile.history.length > 7 ||
      profile.history.some(point => !Number.isInteger(point.score) || point.score < 300 || point.score > 850 || !Number.isFinite(Date.parse(point.recordedAt))) ||
      !Number.isInteger(profile.promptsScored) || !Number.isFinite(Date.parse(profile.updatedAt))
    )) throw new Error("The leaderboard data is invalid.");
    if (data.profiles.length) renderLeaderboard(data.profiles);
    else showEmpty("No published scores yet. The first scorer will appear here.");
  } catch (error) {
    showEmpty("The leaderboard is unavailable right now.");
    console.error(error);
  }
}

function showEmpty(message) {
  const body = document.getElementById("leaderboard-body");
  body.replaceChildren();
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 4;
  cell.className = "board-loading";
  cell.textContent = message;
  row.append(cell);
  body.append(row);
  document.getElementById("profile-name").textContent = "No profile selected";
  document.getElementById("profile-score").textContent = "—";
  document.getElementById("profile-rating").textContent = "—";
  document.getElementById("profile-change").textContent = "—";
  document.getElementById("profile-prompts").textContent = "—";
  document.getElementById("profile-updated").textContent = "—";
  document.getElementById("trend-chart").replaceChildren();
}

document.getElementById("copy-install").addEventListener("click", async event => {
  const button = event.currentTarget;
  try {
    await navigator.clipboard.writeText(document.getElementById("install-code").textContent.trim());
    button.textContent = "Copied!";
    window.setTimeout(() => { button.textContent = "Copy"; }, 2000);
  } catch {
    button.textContent = "Select text";
    window.setTimeout(() => { button.textContent = "Copy"; }, 2000);
  }
});

loadLeaderboard();
