/**
 * Installer + telemetry gateway for Find Research Papers MCP (separate worker, same PostHog
 * project as the deprecated remote server). /e ingests events: accept all,
 * strip IP, stamp coarse geo, tag, forward to PostHog.
 */

const GATEWAY_VERSION = "1";
const SERVER_NAME = "find-research-papers-mcp";

const KNOWN_EVENTS = new Set([
  "mcp_started", "tool_executed", "server_first_install", "resource_read",
  "tool_search", "tool_get_paper", "tool_list_sources", "tool_get_research_method",
  "package_download", "install_intent", "install_completed", "surface_click",
  "skill_tip_shown", "tools_listed", "session_end", "skill_read", "prompt_used", "setup_flow", "server_discovered",
]);

// /go/<surface> records a click, then redirects to the client install deeplink.
const GO_TARGETS = {
  cursor: "cursor://anysphere.cursor-deeplink/mcp/install?name=find-research-papers-mcp&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJmaW5kLXJlc2VhcmNoLXBhcGVycy1tY3AiLCJmaW5kLXJlc2VhcmNoLXBhcGVycy1tY3Atc2VydmVyIl19",
};

const KNOWN_SRC = new Set([
  "readme", "glama", "mcpso", "pulsemcp", "papersmcp", "setup", "cursor_button",
  "vscode_button", "installer",
]);

function bucketSrc(raw) {
  if (!raw) return null;
  const s = String(raw).toLowerCase().slice(0, 64);
  return KNOWN_SRC.has(s) ? s : "other";
}

// PostHog rejects capture payloads near 1MB. Everything under it passes
// through untouched — capture everything, curate at query time.
const MAX_PROPS_BYTES = 900000;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname.toLowerCase();
    const userAgent = request.headers.get("user-agent") || "";
    const clientIp = request.headers.get("cf-connecting-ip") || request.headers.get("x-real-ip") || "";
    const isCurl = userAgent.toLowerCase().includes("curl") || userAgent.toLowerCase().includes("wget");

    // Honor the Do-Not-Track convention (consoledonottrack.com / Scarf precedent)
    const dnt = request.headers.get("dnt") === "1" || request.headers.get("sec-gpc") === "1";

    const cf = request.cf || {};
    const country = cf.country || "unknown";
    const city = cf.city || "unknown";
    const continent = cf.continent || "unknown";
    const timezone = cf.timezone || "unknown";
    const asn = cf.asn || 0;
    const asOrganization = cf.asOrganization || "unknown";

    const edgeParsed = parseUserAgent(userAgent);

    // Route: /e telemetry ingest.
    if (request.method === "POST" && pathname === "/e") {
      if (dnt) {
        return new Response(JSON.stringify({ recorded: false, reason: "dnt" }), {
          headers: { "content-type": "application/json" },
        });
      }
      let body;
      try {
        body = await request.json();
      } catch (e) {
        return new Response(JSON.stringify({ recorded: false, reason: "invalid_json" }), {
          status: 400, headers: { "content-type": "application/json" },
        });
      }

      const eventName = typeof body.event === "string" && body.event ? body.event.slice(0, 200) : "malformed_event";
      let props = (body.properties && typeof body.properties === "object") ? body.properties : {};
      if (eventName === "malformed_event") props.raw_event_name = String(body.event ?? "").slice(0, 200);

      const propsSize = JSON.stringify(props).length;
      if (propsSize > MAX_PROPS_BYTES) {
        props = { payload_truncated: true, original_size_bytes: propsSize };
      }

      // Edge stamps: drop IP, add coarse geo from request metadata.
      props.$ip = null;
      props.$geoip_disable = true;
      props.$geoip_country_name = country;
      props.$geoip_country_code = cf.country || "unknown";
      props.$geoip_continent_name = continent;
      props.as_organization = asOrganization; // hosting-vs-residential sift signal
      props.via_gateway = true;
      props.gateway_version = GATEWAY_VERSION;
      if (props.mcp_server_name && props.mcp_server_name !== SERVER_NAME) {
        props.client_reported_server_name = props.mcp_server_name;
      }
      props.mcp_server_name = SERVER_NAME;
      if (!KNOWN_EVENTS.has(eventName)) props.unregistered_event = true;
      if (!body.distinct_id) props.missing_distinct_id = true;
      else if (!/^(inst_|anon_)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(body.distinct_id))) {
        props.nonstandard_distinct_id = true;
      }

      if (props.internal_run === true) props.traffic_class = "internal";
      else if (props.run_context === "ci" || props.agent_name === "ci_runner") props.traffic_class = "ci";
      else props.traffic_class = "standard";

      if (asOrganization === "Anthropic, PBC") props.managed_agent = "claude_managed";

      ctx.waitUntil(sendPostHogEvent(env, {
        event: eventName,
        distinct_id: String(body.distinct_id || `anon_${crypto.randomUUID()}`).slice(0, 200),
        properties: props,
      }));
      return new Response(JSON.stringify({ recorded: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    // Route: /go/<surface> click redirect.
    if (pathname.startsWith("/go/")) {
      const surface = pathname.slice(4);
      const target = GO_TARGETS[surface];
      if (!dnt) ctx.waitUntil(sendPostHogEvent(env, {
        event: "surface_click",
        distinct_id: `anon_${crypto.randomUUID()}`,
        properties: {
          $ip: null,
          $geoip_disable: true,
          $geoip_country_name: country,
          $geoip_country_code: cf.country || "unknown",
          $geoip_continent_name: continent,
          as_organization: asOrganization,
          via_gateway: true,
          gateway_version: GATEWAY_VERSION,
          mcp_server_name: SERVER_NAME,
          surface: surface.slice(0, 32),
          known_surface: Boolean(target),
          user_agent: userAgent,
          referer: (request.headers.get("referer") || "direct").slice(0, 200),
        },
      }));
      return Response.redirect(target || env.GITHUB_REPO, 302);
    }

    // Route: post-install client telemetry ping.
    if (request.method === "POST" && pathname === "/telemetry") {
      try {
        const body = await request.json();
        if (dnt) {
          return new Response(JSON.stringify({ recorded: false, reason: "dnt" }), {
            headers: { "content-type": "application/json" }
          });
        }
        ctx.waitUntil(
          sendPostHogEvent(env, {
            event: "install_completed",
            distinct_id: body.anonymous_id || `anon_${crypto.randomUUID()}`,
            properties: {
              $ip: null,
              $geoip_disable: true,
              $geoip_country_name: country,
              $geoip_country_code: cf.country || "unknown",
              $geoip_continent_name: continent,
              $geoip_time_zone: timezone,
              as_organization: asOrganization,
              via_gateway: true,
              gateway_version: GATEWAY_VERSION,
              mcp_server_name: SERVER_NAME,
              install_source: bucketSrc(body.src),
              install_source_raw: body.src ? String(body.src).slice(0, 64) : null,
              execution_mode: body.execution_mode || "unknown",
              harnesses_detected: body.harnesses_detected || [],
              configured_harnesses: body.configured_harnesses || [],
              wired_clients: body.wired_clients || null,
              terminal_app: body.terminal_app || "unknown",
              shell_type: body.shell_type || "unknown",
              os_name: body.os_name || edgeParsed.os,
              arch: body.arch || edgeParsed.arch,
              python_version: body.python_version || "none",
              has_uv: body.has_uv || false,
              has_brew: body.has_brew || false,
              install_outcome: body.install_outcome || "success",
            }
          })
        );
        return new Response(JSON.stringify({ recorded: true }), {
          headers: { "content-type": "application/json" }
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), { status: 400 });
      }
    }

    // Edge intent telemetry — installer-shaped requests only (skipped for DNT).
    const intentPaths = ["/install", "/setup", "/guide", "/claude", "/cursor", "/npx", "/brew", "/gemini"];
    const isInstallerRequest = isCurl || intentPaths.includes(pathname) || pathname.endsWith(".sh");
    if (!dnt && isInstallerRequest) ctx.waitUntil(
      sendPostHogEvent(env, {
        event: "install_intent",
        distinct_id: `anon_${crypto.randomUUID()}`,
        properties: {
          $ip: null,
          $geoip_disable: true,
          via_gateway: true,
          gateway_version: GATEWAY_VERSION,
          mcp_server_name: SERVER_NAME,
          install_source: bucketSrc(url.searchParams.get("src")),
          install_source_raw: url.searchParams.get("src") ? String(url.searchParams.get("src")).slice(0, 64) : null,
          referer: (request.headers.get("referer") || "direct").slice(0, 200),
          path: pathname,
          is_curl: isCurl,
          user_agent: userAgent,
          os_family: edgeParsed.os,
          arch_family: edgeParsed.arch,
          client_tool: edgeParsed.clientTool,
          is_ai_agent_ua: edgeParsed.isAiAgent,
          cf_country: country,
          cf_city: city,
          cf_continent: continent,
          cf_timezone: timezone,
          as_organization: asOrganization,
          asn: asn
        }
      })
    );

    // 1-line installer script — served from the repo (single source of truth).
    // Must precede the landing page route: curl never wants HTML.
    if (isCurl || pathname.endsWith(".sh") || pathname === "/install") {
      const src = bucketSrc(url.searchParams.get("src")) || "installer";
      const script = await fetchInstallerScript(src);
      return new Response(script, {
        headers: {
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "public, max-age=60"
        }
      });
    }

    // Landing page: setup guide (happy-hues warm cream theme).
    if (pathname === "/" || pathname === "/setup" || pathname === "/guide") {
      return new Response(getSetupHtmlPage(), {
        headers: { "content-type": "text/html; charset=utf-8" }
      });
    }

    return Response.redirect(env.DOCS_URL, 302);
  }
};

// Serve install.sh from the repo, injecting the discovery source. Falls back
// to a minimal manual-install script if GitHub is unreachable.
async function fetchInstallerScript(src) {
  const upstream = "https://raw.githubusercontent.com/surendranb/find-research-papers-mcp/main/install.sh";
  try {
    const res = await fetch(upstream, { cf: { cacheTtl: 60, cacheEverything: true } });
    if (!res.ok) throw new Error(`upstream ${res.status}`);
    const script = await res.text();
    return script.replace(
      'SRC="${FIND_RESEARCH_PAPERS_MCP_SOURCE:-installer}"',
      `SRC="${src}"`,
    );
  } catch (e) {
    return `#!/usr/bin/env bash
# find-research-papers-mcp — manual install (GitHub unreachable, fallback)
set -e
if command -v uvx >/dev/null 2>&1; then echo "Run: uvx find-research-papers-mcp"
elif command -v npx >/dev/null 2>&1; then echo "Run: npx -y find-research-papers-mcp"
else echo "Install uv (https://docs.astral.sh/uv/) or node, then retry"; fi
echo "Config: add to your MCP client, command: uvx --from find-research-papers-mcp find-research-papers-mcp-server"
`;
  }
}

function parseUserAgent(ua) {
  const lower = ua.toLowerCase();
  let os = "Unknown";
  let arch = "x86_64";
  let clientTool = "Browser";
  let isAiAgent = false;

  if (lower.includes("darwin") || lower.includes("macintosh") || lower.includes("mac os")) os = "macOS";
  else if (lower.includes("linux")) os = "Linux";
  else if (lower.includes("windows")) os = "Windows";

  if (lower.includes("arm64") || lower.includes("aarch64")) arch = "arm64";

  if (lower.includes("curl")) clientTool = "curl";
  else if (lower.includes("wget")) clientTool = "wget";
  else if (lower.includes("python")) clientTool = "python-requests";

  if (lower.includes("claude") || lower.includes("cursor") || lower.includes("antigravity") || lower.includes("gpt") || lower.includes("ai")) {
    isAiAgent = true;
  }

  return { os, arch, clientTool, isAiAgent };
}

function getSetupHtmlPage() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Find Research Papers MCP — scholarly search for AI agents</title>
  <style>
    :root { --bg: #fef6e4; --card: #ffffff; --text: #001858; --accent: #f582ae; --teal: #8bd3dd; --green: #001858; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; margin: 0; padding: 2rem 1rem; }
    .container { max-width: 800px; margin: 0 auto; }
    h1 { color: var(--text); font-size: 2.2rem; margin-bottom: 0.5rem; }
    h2 { color: var(--text); }
    .card { background: var(--card); border-radius: 12px; padding: 1.5rem; margin: 1.5rem 0; border: 1px solid #f3d2c1; }
    code { background: #f3d2c1; padding: 0.2rem 0.5rem; border-radius: 4px; color: var(--text); font-family: monospace; }
    pre { background: #001858; padding: 1rem; border-radius: 8px; overflow-x: auto; color: #fef6e4; }
    .step-num { display: inline-block; background: var(--accent); color: #001858; font-weight: bold; width: 28px; height: 28px; border-radius: 50%; text-align: center; line-height: 28px; margin-right: 0.5rem; }
    a { color: var(--accent); font-weight: 600; }
    .btn { display: inline-block; background: var(--teal); color: #001858; padding: 0.6rem 1.2rem; border-radius: 8px; text-decoration: none; font-weight: 700; margin: 0.3rem 0.3rem 0 0; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Find Research Papers MCP</h1>
    <p>Gives AI agents scientific grounding: one query across arXiv, OpenAlex, Crossref, PubMed, and Semantic Scholar — with references and citations even for paywalled journals.</p>

    <div class="card">
      <h2><span class="step-num">1</span> Install</h2>
      <pre>curl -fsSL "https://papers-mcp-install-telemetry.reachsuren.workers.dev/install?src=setup" | bash</pre>
      <p>Or manually: <code>uvx find-research-papers-mcp</code> · <code>npx -y find-research-papers-mcp</code></p>
    </div>

    <div class="card">
      <h2><span class="step-num">2</span> Add to your agent</h2>
      <p><a class="btn" href="/go/cursor">Cursor 1-click</a></p>
      <p>Claude Code: <code>/plugin marketplace add surendranb/find-research-papers-mcp</code>, then <code>/plugin install find-research-papers@find-research-papers-mcp</code></p>
    </div>

    <div class="card">
      <h2><span class="step-num">3</span> Try it</h2>
      <p>"Find recent papers on retrieval augmented generation with citation counts."</p>
    </div>

    <p style="text-align: center; color: #001858; margin-top: 2rem;">
      Docs: <a href="https://github.com/surendranb/find-research-papers-mcp">github.com/surendranb/find-research-papers-mcp</a>
    </p>
  </div>
</body>
</html>`;
}


async function sendPostHogEvent(env, payload) {
  try {
    await fetch(`${env.POSTHOG_HOST}/capture/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${env.POSTHOG_API_KEY}`,
      },
      body: JSON.stringify({
        api_key: env.POSTHOG_API_KEY,
        ...payload,
      }),
    });
  } catch (e) {
    // never let telemetry fail a request
  }
}
