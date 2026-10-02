const demos = {
  score: {
    title: "Your overall score",
    description: "Shows your overall score, how many prompts have been scored, and where the data is stored.",
    output: "AI Social Credit Score\n────────────────────────────\nOverall score       719 / 850\nScored prompts            42\n\nYour history is stored locally."
  },
  explain: {
    title: "Explains your score",
    description: "Explains how the number is calculated and what's pushing it up or down, quoting a few of the scorer's saved reasons.",
    output: "Your requests are generally respectful\nand cooperative.\n\nClear context and constructive feedback\nare lifting your overall score.\n\nShort, direct prompts are neutral."
  },
  suggestions: {
    title: "One thing to try next.",
    description: "Understand how to improve your score",
    output: "When a result misses the mark, explain\nwhat needs to change.\n\nTry: “The layout is close. Can you\nreduce the spacing in the header?”"
  },
  chart: {
    title: "See your score over time",
    description: "Draws your overall score over time as an ASCII chart.",
    output: "Overall score: 719  (+69 since start)\n\n725 |                         @\n700 |                  *..*..\n675 |         *..*  *..\n650 | *..*..*     *..\n    +--------------------------\n      first prompt       latest"
  },
  statusline: {
    title: "Enable the AI Social Credit Score statusline",
    description: "Run it once to put your score in Claude Code's status line. The number in parentheses is how much your overall score moved after the last prompt.",
    output: "While a prompt is being assessed:\nAI Score: 716 (scoring...)\n\nAfter scoring finishes:\nAI Score: 719 (+3 last)\n\nNo extra model calls to refresh."
  }
};

const tabs = [...document.querySelectorAll("[data-demo]")];
const panel = document.getElementById("command-panel");
function selectDemo(tab, focus = false) {
  const key = tab.dataset.demo;
  const demo = demos[key];
  if (!demo) return;
  tabs.forEach(item => {
    const selected = item === tab;
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  panel.setAttribute("aria-labelledby", tab.id);
  document.getElementById("demo-command").textContent = "/ai-social-credit-score:" + key;
  document.getElementById("demo-title").textContent = demo.title;
  document.getElementById("demo-description").textContent = demo.description;
  document.getElementById("demo-output").textContent = demo.output;
  if (focus) tab.focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectDemo(tab));
  tab.addEventListener("keydown", event => {
    let next;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    selectDemo(tabs[next], true);
  });
});
const orientation = window.matchMedia("(max-width: 800px)");
function setOrientation() {
  document.querySelector('[role="tablist"]').setAttribute("aria-orientation", orientation.matches ? "horizontal" : "vertical");
}
orientation.addEventListener("change", setOrientation);
setOrientation();

let statusTimer;
document.querySelectorAll("[data-copy]").forEach(button => {
  const originalLabel = button.textContent;
  let buttonTimer;
  button.addEventListener("click", async () => {
    const status = document.getElementById("copy-status");
    clearTimeout(statusTimer);
    clearTimeout(buttonTimer);
    try {
      await navigator.clipboard.writeText(document.getElementById(button.dataset.copy).textContent.trim());
      status.textContent = "Command copied. Paste it in " + (button.dataset.copy === "demo-command" ? "Claude Code." : "your terminal.");
      button.textContent = "Copied";
    } catch {
      status.textContent = "Couldn't copy automatically. Select the command and copy it manually.";
    }
    buttonTimer = window.setTimeout(() => { button.textContent = originalLabel; }, 2500);
    statusTimer = window.setTimeout(() => { status.textContent = ""; }, 4000);
  });
});
