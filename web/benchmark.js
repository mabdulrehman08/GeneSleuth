const status = document.getElementById("benchmark-status");
const output = document.getElementById("benchmark-report");

function add(parent, tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  parent.append(element);
  return element;
}

function cells(line) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((value) => value.trim());
}

function plain(line) {
  return line.replace(/\*\*([^*]+)\*\*|\x60([^\x60]+)\x60/g, (_, bold, code) => bold || code);
}

function render(report) {
  const lines = report.split(/\r?\n/);
  let list;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (line.startsWith("|") && /^\|[\s:|-]+$/.test(lines[i + 1]?.trim() || "")) {
      const wrapper = add(output, "div", "");
      wrapper.className = "table-wrap";
      const table = add(wrapper, "table", "");
      const header = add(add(table, "thead", ""), "tr", "");
      for (const value of cells(line)) add(header, "th", plain(value)).scope = "col";
      const body = add(table, "tbody", "");
      i += 1;
      while (lines[i + 1]?.trim().startsWith("|")) {
        i += 1;
        const row = add(body, "tr", "");
        for (const value of cells(lines[i])) add(row, "td", plain(value));
      }
      list = undefined;
    } else if (/^[-*] /.test(line)) {
      list ||= add(output, "ul", "");
      add(list, "li", plain(line.slice(2)));
    } else {
      list = undefined;
      const heading = line.match(/^(#{1,6})\s+(.+)/);
      if (heading) add(output, heading[1].length < 3 ? "h2" : "h3", plain(heading[2]));
      else if (line && !line.startsWith("![")) add(output, "p", plain(line));
    }
  }
}

async function benchmark() {
  try {
    const response = await fetch("/api/benchmark");
    if (!response.ok) throw new Error("Benchmark results are unavailable.");
    const data = await response.json();
    if (data.status === "pending") {
      status.textContent = "Held-out test results have not been published yet. Check back after the DEV and TEST runs finish.";
      return;
    }
    status.hidden = true;
    document.getElementById("benchmark-figure").hidden = !data.chart;
    if (data.chart) document.getElementById("benchmark-chart").src = "/api/benchmark/chart";
    render(data.report);
  } catch (error) {
    status.textContent = error.message;
  }
}
benchmark();
