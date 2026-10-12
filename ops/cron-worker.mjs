// Optional backup research trigger. Does not publish or receive Meta/AI credentials.
const PANEL = 'https://ntekintr.github.io/seferihisarofficial-news/data.json';
const WORKFLOW = 'https://api.github.com/repos/ntekintr/seferihisarofficial-news/actions/workflows/automation.yml';

export async function checkResearch(env, fetcher = fetch, now = Date.now()) {
  if (env.CRON_DISPATCH_ENABLED !== 'true' || !env.GITHUB_ACTIONS_TOKEN) return {status:'disabled'};
  let stage = 'panel_fetch';
  try {
    const publicResponse = await fetcher(PANEL, {cache:'no-store', redirect:'manual'});
    if (!publicResponse.ok) return {status:'panel_unreachable'};
    stage = 'panel_parse';
    const state = await publicResponse.json();
    const finished = Date.parse(state.runs?.find(r=>r.finished_at)?.finished_at || '');
    if (state.demo !== false || !Number.isFinite(finished) || finished > now + 300000) return {status:'invalid_state'};
    if (now - finished < 20 * 60000) return {status:'fresh'};
    const headers = {'Authorization':'Bearer '+env.GITHUB_ACTIONS_TOKEN, 'Accept':'application/vnd.github+json',
                     'User-Agent':'SeferihisarOfficialResearchWatch', 'X-GitHub-Api-Version':'2022-11-28'};
    stage = 'github_fetch';
    const runsResponse = await fetcher(WORKFLOW+'/runs?branch=main&per_page=5', {headers, redirect:'manual'});
    if (!runsResponse.ok) return {status:'github_unreachable'};
    stage = 'github_parse';
    const runs = await runsResponse.json();
    if (!Array.isArray(runs.workflow_runs)) return {status:'invalid_runs'};
    if (runs.workflow_runs.some(r=>r.head_branch==='main' && ['queued','in_progress','waiting','requested','pending'].includes(r.status))) return {status:'already_running'};
    // A just-completed run can still be waiting for CDN propagation. Do not queue twice.
    if (runs.workflow_runs.some(r=>r.head_branch==='main' && now-Date.parse(r.created_at)<20*60000)) return {status:'recent_run'};
    stage = 'dispatch';
    const dispatch = await fetcher(WORKFLOW+'/dispatches', {method:'POST', headers:{...headers,'Content-Type':'application/json'},
                                   body:JSON.stringify({ref:'main'}), redirect:'manual'});
    return {status:dispatch.status===204?'dispatched':'dispatch_failed'};
  } catch (error) {
    const error_type = ['TypeError','SyntaxError','RangeError'].includes(error?.name) ? error.name : 'Error';
    const message = String(error?.message || '').toLowerCase();
    const cause = message.includes('unsupported cache') ? 'cache_mode' : message.includes('illegal invocation') ? 'fetch_receiver' : message.includes('redirect') ? 'redirect_refused' : 'request_failed';
    return {status:'check_failed',stage,error_type,cause}; // Never log a request, token, provider body or raw exception.
  }
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(checkResearch(env).then(result=>console.log(JSON.stringify(result))));
  },
  async fetch() {
    return new Response('SeferihisarOfficial research check. Scheduled execution only.', {status:200});
  }
};
