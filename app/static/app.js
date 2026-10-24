(() => {
  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();
  const initData = tg?.initData || "";
  const $ = (id) => document.getElementById(id);
  let lastPreview = null;
  let toastTimer;
  const headers = {"Content-Type":"application/json","X-Telegram-Init-Data":initData};

  function toast(message) {
    const el = $("toast"); el.textContent = message; el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }
  async function api(path, options={}) {
    const response = await fetch(path, {...options, headers:{...headers,...(options.headers||{})}});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.error || `Request failed (${response.status})`);
    return data;
  }
  function currentChannel() { return $("channel").value.trim(); }
  function cleanUsername(id) { return $(id).value.trim().replace(/^@/,""); }
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  async function boot() {
    if (!initData) {
      $("auth-status").textContent = "Open inside Telegram";
      toast("Open this dashboard from your Telegram bot's Web App button.");
      return;
    }
    try {
      const me = await api("/api/me");
      $("auth-status").textContent = `Admin ${me.user_id}`;
      await Promise.all([loadChannels(),loadJobs()]);
    } catch (e) { $("auth-status").textContent = "Not authorized"; toast(e.message); }
  }
  async function loadChannels() {
    const data = await api("/api/channels");
    $("channel-list").innerHTML = data.channels.length ? data.channels.map(c =>
      `<div class="item"><div class="item-head"><span>${esc(c.title || c.channel_key)}</span><span class="status">${esc(c.scan_status || "added")}</span></div><div class="muted">${esc(c.channel_key)} · ${esc(c.username ? "@"+c.username : c.resolved_id || "")}</div></div>`
    ).join("") : `<p class="muted">No channels added yet.</p>`;
  }
  async function loadJobs() {
    const data = await api("/api/jobs");
    $("jobs").innerHTML = data.jobs.length ? data.jobs.map(j => {
      const progress = j.type === "scan" ? `${j.scanned_count || 0} scanned` : `${j.updated_buttons || 0} buttons updated · ${j.failed_posts || 0} failed`;
      return `<div class="item"><div class="item-head"><span>${esc(j.type)} · ${esc(j.channel_key)}</span><span class="status">${esc(j.status)}</span></div><div class="muted">${esc(j.job_id)} · ${esc(progress)}</div>${j.last_error?`<div style="color:#ff9292;margin-top:5px">${esc(j.last_error)}</div>`:""}</div>`;
    }).join("") : `<p class="muted">No jobs yet.</p>`;
  }
  async function addChannel(scan=false, monitor=false) {
    const channel = currentChannel(); if (!channel) return toast("Enter a channel first.");
    let payload = {channel};
    if (monitor) {
      const old_username = cleanUsername("old-user"), new_username = cleanUsername("new-user");
      if (!old_username || !new_username) throw new Error("Enter both old and replacement bot usernames before enabling monitoring.");
      payload = {...payload, old_username, new_username};
    }
    const data = await api(scan?"/api/scan":monitor?"/api/monitor":"/api/channels",{method:"POST",body:JSON.stringify(payload)});
    toast(scan ? `Scan queued: ${data.job_id}` : monitor ? "New-post auto-recovery enabled." : "Channel added.");
    await loadChannels(); await loadJobs();
  }
  function replacementBody() {
    const channel_key = currentChannel(), old_username = cleanUsername("old-user"), new_username = cleanUsername("new-user");
    if (!channel_key) throw new Error("Enter the channel username or ID.");
    if (!old_username || !new_username) throw new Error("Enter both old and replacement bot usernames.");
    return {channel_key,old_username,new_username,preview_limit:10000};
  }
  async function preview() {
    const body = replacementBody();
    lastPreview = null; $("apply").disabled = true;
    const result = await api("/api/preview",{method:"POST",body:JSON.stringify(body)});
    lastPreview = body;
    $("preview-result").classList.remove("hidden");
    $("preview-result").innerHTML = `<div class="stat-row"><div class="stat"><b>${result.matching_posts}</b><span>matching posts</span></div><div class="stat"><b>${result.matching_buttons}</b><span>matching buttons</span></div></div>
      <p class="muted">Review sample changes below. The exact start token is retained.</p>
      ${result.sample.map(post=>`<div class="sample"><strong>Post #${post.message_id}</strong><br>${esc(post.text_preview || "[Media / no text]")}<br>${post.matches.map(m=>`<p><span class="muted">${esc(m.label || "Button")}</span><br><code>${esc(m.old_url)}</code><br>→ <code>${esc(m.new_url)}</code></p>`).join("")}</div>`).join("") || `<p class="muted">No matches. Scan this channel first, and verify the old username.</p>`}`;
    $("apply").disabled = result.matching_buttons === 0;
    toast(`Preview ready: ${result.matching_buttons} button(s).`);
  }
  async function apply() {
    if (!lastPreview) return toast("Preview changes before applying.");
    if (!confirm("Apply this recovery job? Only matching button URLs will change. This action edits existing channel posts.")) return;
    const result = await api("/api/replace",{method:"POST",body:JSON.stringify({...lastPreview,confirm:true})});
    $("apply").disabled = true; lastPreview = null;
    toast(`Recovery job queued: ${result.job_id}`);
    await loadJobs();
  }
  async function searchPosts() {
    const channel = currentChannel(); if (!channel) return toast("Enter a channel first.");
    const q = $("search").value.trim();
    const data = await api(`/api/posts?channel=${encodeURIComponent(channel)}&q=${encodeURIComponent(q)}&page=1`);
    $("posts").innerHTML = data.posts.length ? data.posts.map(p => `<div class="item"><div class="item-head"><span>Post #${p.message_id}</span><span class="muted">${p.button_count || 0} buttons</span></div><p>${esc(p.text_preview || "[Media / no text]")}</p>${(p.buttons||[]).map(b=>`<div class="muted">${esc(b.label || "Button")}: ${esc(b.url || `[${b.button_type}]`)}</div>`).join("")}</div>`).join("") : `<p class="muted">No indexed posts found.</p>`;
  }
  $("add-channel").addEventListener("click",()=>addChannel().catch(e=>toast(e.message)));
  $("scan").addEventListener("click",()=>addChannel(true).catch(e=>toast(e.message)));
  $("monitor").addEventListener("click",()=>addChannel(false,true).catch(e=>toast(e.message)));
  $("preview").addEventListener("click",()=>{try{preview().catch(e=>toast(e.message));}catch(e){toast(e.message);}});
  $("apply").addEventListener("click",()=>apply().catch(e=>toast(e.message)));
  $("refresh-jobs").addEventListener("click",()=>loadJobs().catch(e=>toast(e.message)));
  $("search-posts").addEventListener("click",()=>searchPosts().catch(e=>toast(e.message)));
  boot();
  setInterval(()=>{ if(initData) loadJobs().catch(()=>{}); },10000);
})();
