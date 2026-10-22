(() => {
  const token = document.querySelector('meta[name="drc-token"]').content;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = {
    data: null,
    page: 'overview',
    gameId: null,
    currentGame: null,
    platformFilter: 'all',
    search: '',
    expandedRoots: new Set(),
    rootFiles: new Map(),
    scanTimers: new Map(),
    toastTimer: null,
  };

  const labels = {
    PS4: 'پلی‌استیشن ۴', PS5: 'پلی‌استیشن ۵',
    updates: 'به‌روزرسانی', DLC: 'محتوای اضافه', subtitles: 'زیرنویس', themes: 'تم', homebrew: 'هوم‌برو',
    not_checked: 'بررسی نشده', checked_found: 'یافته ثبت شده', checked_no_result: 'بدون نتیجه',
    unavailable: 'در دسترس نیست', blocked_by_policy: 'مسدود با خط‌مشی', unsupported: 'پشتیبانی نمی‌شود',
    stale: 'کهنه', error: 'خطا', exact_match: 'شناسه دقیق', likely_match: 'احتمالاً سازگار',
    needs_review: 'نیازمند بازبینی', incompatible: 'ناسازگار', unknown: 'نامشخص', already_present: 'موجود در پوشه',
    official: 'رسمی', maintained_community: 'جامعهٔ نگه‌داری‌شده', unverified: 'تأییدنشده', blocked: 'مسدود',
    healthy: 'فعال', limited: 'محدود', available: 'در دسترس', scanning: 'در حال اسکن',
    complete: 'کامل', partial: 'ناقص', cancelled: 'لغوشده', running: 'در حال اجرا',
    awaiting_approval: 'در انتظار تأیید', approved: 'تأیید شده', queued: 'در صف', downloading: 'در حال دریافت',
    completed: 'دریافت کامل', failed: 'ناموفق', rejected: 'رد شده', approval_expired: 'تأیید منقضی',
    verification_failed: 'بررسی هش ناموفق', paused: 'متوقف‌شده', user_asserted: 'اظهار کاربر', imported: 'واردشده',
    source_reported: 'گزارش منبع', inferred: 'تشخیص احتمالی', user_confirmed: 'تأیید کاربر',
  };
  const pageTitles = {
    overview: ['نمای کلی کتابخانه', 'کتابخانه بازی شما'], games: ['مجموعهٔ شخصی', 'بازی‌ها'],
    sources: ['رجیستری منبع', 'منابع'], roots: ['فهرست محلی', 'پوشه‌های محلی'],
    queue: ['تأیید موردی', 'صف دریافت'], settings: ['تنظیمات محلی', 'تنظیمات'], detail: ['جزئیات بازی', 'جزئیات بازی'],
  };

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }
  function faNum(value) {
    return new Intl.NumberFormat('fa-IR').format(Number(value || 0));
  }
  function fmtDate(value) {
    if (!value) return 'ثبت نشده';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return esc(value);
    return new Intl.DateTimeFormat('fa-IR', {dateStyle:'medium',timeStyle:'short'}).format(date);
  }
  function fmtBytes(value) {
    if (value === null || value === undefined || value === '') return 'نامشخص';
    const n = Number(value);
    if (!Number.isFinite(n)) return 'نامشخص';
    const units = ['B','KB','MB','GB','TB'];
    let amount = n, unit = 0;
    while (amount >= 1000 && unit < units.length - 1) { amount /= 1000; unit += 1; }
    return `${new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(amount)} ${units[unit]}`;
  }
  function label(key) { return labels[key] || key || 'نامشخص'; }
  function statusBadge(status) { return `<span class="state-badge ${esc(status)}">${esc(label(status))}</span>`; }
  function trustBadge(trust) { return `<span class="tier ${esc(trust)}">${esc(label(trust))}</span>`; }
  function normalize(value) {
    return String(value || '').normalize('NFKC').toLocaleLowerCase('fa-IR')
      .replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/[ۀة]/g,'ه')
      .replace(/[ـ\u200c\u200d\ufeff]/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim().replace(/\s+/g,' ');
  }
  function normalizeId(value) { return String(value || '').toUpperCase().replace(/[^A-Z0-9]/g,''); }
  async function api(path, options = {}) {
    const headers = {'X-DRC-Token': token, ...(options.headers || {})};
    let body = options.body;
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(body); }
    const response = await fetch(path, {...options, headers, body, cache:'no-store'});
    let value;
    try { value = await response.json(); } catch { value = {}; }
    if (!response.ok) throw new Error(value.error || `درخواست با خطای ${response.status} روبه‌رو شد.`);
    return value;
  }
  function toast(message, error = false) {
    const node = $('#toast');
    node.textContent = message;
    node.classList.toggle('error', error);
    node.classList.add('show');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => node.classList.remove('show'), 3300);
  }
  function openModal(html) {
    $('#modal-content').innerHTML = `<div class="modal-content">${html}</div>`;
    $$('.form-field',$('#modal-content')).forEach((field,index)=>{
      const labelNode = field.querySelector(':scope > label');
      const control = field.querySelector(':scope > input, :scope > select, :scope > textarea') || field.querySelector(':scope > .path-entry > input, :scope > .path-entry > select');
      if (labelNode && control && !control.id) {
        control.id = `modal-field-${index}`;
        labelNode.htmlFor = control.id;
      }
    });
    const dialog = $('#modal');
    if (!dialog.open) dialog.showModal();
  }
  function closeModal() { if ($('#modal').open) $('#modal').close(); }
  function nav(page) {
    state.page = page;
    $$('.page').forEach(node => node.classList.toggle('active', node.dataset.page === page));
    $$('.nav-item[data-page]').forEach(node => node.classList.toggle('active', node.dataset.page === page || (page === 'detail' && node.dataset.page === 'games')));
    const info = pageTitles[page] || pageTitles.overview;
    $('#breadcrumb').textContent = page === 'detail' && state.currentGame ? `بازی‌ها / ${state.currentGame.display_title || state.currentGame.canonical_title}` : info[0];
    $('#page-title').textContent = page === 'detail' && state.currentGame ? (state.currentGame.display_title || state.currentGame.canonical_title) : info[1];
    if (page === 'overview') renderOverview();
    if (page === 'games') renderGames();
    if (page === 'sources') renderSources();
    if (page === 'roots') renderRoots();
    if (page === 'queue') renderJobs();
    if (page === 'settings') renderSettings();
    window.scrollTo({top:0,behavior:'smooth'});
  }
  async function refresh() {
    state.data = await api('/api/bootstrap');
    renderNavCounts();
    if (state.page === 'overview') renderOverview();
    if (state.page === 'games') renderGames();
    if (state.page === 'sources') renderSources();
    if (state.page === 'roots') renderRoots();
    if (state.page === 'queue') renderJobs();
    if (state.page === 'settings') renderSettings();
    if (state.page === 'detail' && state.gameId) await openGame(state.gameId, false);
  }
  function renderNavCounts() {
    if (!state.data) return;
    $('#nav-game-count').textContent = faNum(state.data.counts.games);
    $('#nav-source-count').textContent = faNum(state.data.counts.sources);
    $('#nav-queue-count').textContent = faNum(state.data.counts.pending_approvals);
  }
  function renderOverview() {
    if (!state.data) return;
    const c = state.data.counts;
    $('#stats-strip').innerHTML = [
      [c.games,'بازی ثبت‌شده'], [c.sources,'منبع در رجیستری'], [c.local_files,'فایل در پوشه‌های ثبت‌شده'], [c.pending_approvals,'در انتظار تصمیم شما'],
    ].map(([num,text]) => `<div class="stat-cell"><strong>${faNum(num)}</strong><span>${esc(text)}</span></div>`).join('');
    const games = state.data.games.slice(0,5);
    $('#overview-games').innerHTML = games.length
      ? `<div class="game-list">${games.map(renderGameRow).join('')}</div>`
      : `<div class="empty-state"><h3>کتابخانه هنوز بازی ندارد</h3><p>یک عنوان را دستی ثبت کنید یا فایل CSV/JSON را پیش از ورود مرور کنید.</p><button class="button button-outline button-small" data-action="add-game">ثبت اولین بازی</button></div>`;
    const activity = state.data.recent_activity || [];
    $('#recent-activity').innerHTML = activity.length
      ? `<div class="activity-list">${activity.map(item => `<div class="activity-item"><i class="activity-mark"></i><div><p>${esc(activityText(item))}</p><time>${esc(fmtDate(item.timestamp))}</time></div></div>`).join('')}</div>`
      : `<div class="empty-block"><strong>هنوز رویدادی ثبت نشده</strong>افزودن بازی، بررسی منبع و اسکن پوشه‌ها در اینجا ثبت می‌شوند.</div>`;
  }
  function activityText(item) {
    const text = {
      game_added: 'بازی به‌صورت دستی به مجموعه افزوده شد', game_imported: 'بازی از فایل وارد شد',
      source_added: 'منبع جدید در رجیستری ثبت شد', source_updated: 'خط‌مشی یا اطلاعات منبع تغییر کرد',
      local_root_selected: 'یک پوشه برای اسکن ثبت شد', source_check_recorded: 'نتیجهٔ بررسی منبع ثبت شد',
      candidate_recorded: 'یک نامزد محتوا با منشأ منبع ثبت شد', candidate_observation_added: 'شاهد منبع دیگری به نامزد موجود پیوند خورد', compatibility_assessed: 'سازگاری نامزد دوباره ارزیابی شد',
      download_approval_requested: 'درخواست تأیید دریافت ایجاد شد', download_approved: 'درخواست دریافت تأیید شد',
      download_rejected: 'درخواست دریافت رد شد', download_completed: 'دریافت فایل کامل شد', download_failed: 'دریافت فایل ناموفق بود',
      download_cancelled: 'دریافت لغو شد', preferences_updated: 'تنظیمات محلی تغییر کرد',
    };
    return text[item.event_type] || `رویداد ${item.event_type}`;
  }
  function renderGameRow(game) {
    const platform = (game.platforms || []).includes('PS5') ? 'PS5' : ((game.platforms || [])[0] || 'PS4');
    const ids = [...(game.title_ids || []), ...(game.product_codes || [])].filter(Boolean).slice(0,2).join(' / ');
    return `<div class="game-row" role="button" tabindex="0" data-game="${esc(game.id)}">
      <span class="game-spine ${platform.toLowerCase()}">${esc(platform)}</span>
      <span class="game-title"><strong>${esc(game.display_title || game.canonical_title)}</strong><span>${faNum(game.owned_count)} ثبت مالکیت</span></span>
      <span class="game-meta"><span>شناسه</span><bdi class="ltr">${esc(ids || 'ثبت نشده')}</bdi></span>
      <span class="game-meta region-col"><span>پلتفرم / ناحیه</span><b>${esc((game.platforms || []).join('، ') || 'نامشخص')} / ${esc((game.regions || []).join('، ') || '—')}</b></span>
      <span class="game-arrow" aria-hidden="true">‹</span>
    </div>`;
  }
  function renderGames() {
    if (!state.data) return;
    const q = normalize(state.search);
    const qId = normalizeId(state.search);
    const games = state.data.games.filter(game => {
      if (state.platformFilter !== 'all' && !(game.platforms || []).includes(state.platformFilter)) return false;
      if (!q) return true;
      const haystack = [game.canonical_title, ...(game.names || []).map(n => n.value), ...(game.title_ids || []), ...(game.product_codes || []), ...(game.regions || []), ...(game.platforms || [])].join(' ');
      return normalize(haystack).includes(q) || (qId && [...(game.title_ids || []), ...(game.product_codes || [])].some(id => normalizeId(id).includes(qId)));
    });
    $('#game-count-label').textContent = `${faNum(games.length)} عنوان`;
    $('#game-list').innerHTML = games.length ? games.map(renderGameRow).join('') : `<div class="empty-block"><strong>${state.data.games.length ? 'جست‌وجویی پیدا نشد' : 'مجموعه خالی است'}</strong>${state.data.games.length ? 'نام، شناسه یا فیلتر پلتفرم را تغییر دهید.' : 'برای شروع یک عنوان PS4 یا PS5 اضافه کنید.'}</div>`;
  }
  async function openGame(gameId, changePage = true) {
    try {
      const game = await api(`/api/games/${encodeURIComponent(gameId)}`);
      state.currentGame = game;
      state.gameId = gameId;
      renderGameDetail(game);
      if (changePage) nav('detail');
      else {
        $('#breadcrumb').textContent = `بازی‌ها / ${game.display_title || game.canonical_title}`;
        $('#page-title').textContent = game.display_title || game.canonical_title;
      }
    } catch (error) { toast(error.message, true); }
  }
  function renderGameDetail(game) {
    const releases = game.releases || [];
    const ids = releases.flatMap(r => [r.title_id, r.product_code]).filter(Boolean);
    const nameRows = (game.names || []).filter(n => n.name_type !== 'language_evidence');
    const platform = releases[0]?.platform || 'PS4';
    const releaseMarkup = releases.map((release, index) => {
      const coverage = (game.coverage || []).filter(row => row.release_id === release.id);
      const content = release.candidates || [];
      const local = release.local_files || [];
      return `<section class="detail-release" id="release-${esc(release.id)}">
        <div class="detail-section-heading"><div><h3>${esc(label(release.platform))}${release.region ? ` · ${esc(release.region)}` : ''}</h3><p class="ltr">${esc(release.title_id || release.product_code || 'شناسه ثبت نشده')}</p></div>
          <div class="detail-actions"><button class="button button-outline button-small" data-action="add-candidate" data-release="${esc(release.id)}">ثبت یافتهٔ منبع</button><button class="button button-quiet button-small" data-action="record-check" data-release="${esc(release.id)}">ثبت نتیجهٔ بررسی</button></div></div>
        <div class="coverage-wrap"><table class="coverage-table"><thead><tr><th>منبع و اعتماد</th><th>دسته</th><th>پوشش</th><th>آخرین بررسی</th><th>نامزد / زبان</th><th>دلیل</th></tr></thead><tbody>
          ${coverage.length ? coverage.map(row => `<tr><td class="source-cell"><strong>${esc(row.source_name)}</strong>${trustBadge(row.trust_tier)}${row.source_enabled?'':'<span class="chip">غیرفعال</span>'}</td><td>${esc(label(row.category))}</td><td>${statusBadge(row.state)}</td><td dir="ltr">${esc(fmtDate(row.checked_at))}</td><td>${faNum(row.candidate_count)} نامزد · ${faNum(row.observation_count)} مشاهده${row.languages.length ? `<span class="coverage-reason" dir="ltr">${esc(row.languages.join(', '))}</span>` : ''}</td><td><span class="coverage-reason">${esc(row.reason)}</span></td></tr>`).join('') : `<tr><td colspan="6">منبعی ثبت نشده است.</td></tr>`}
        </tbody></table></div>
        <div class="detail-section"><div class="detail-section-heading"><div><h3>نامزدهای محتوا</h3><p>زبان فهرست از زبان محتوای اعلام‌شده جدا است.</p></div><span class="quiet-label">${faNum(content.length)} مورد</span></div>
          ${content.length ? content.map(item => renderCandidate(item)).join('') : `<div class="empty-block"><strong>نامزدی ثبت نشده</strong>پس از بررسی یک منبع، مشخصات فهرست و شواهد آن را دستی ثبت کنید.</div>`}
        </div>
        <div class="detail-section"><div class="detail-section-heading"><div><h3>فایل‌های محلی مرتبط</h3><p>فقط تطبیق شناسه یا پیوندی که شما تأیید کرده‌اید.</p></div><span class="quiet-label">${faNum(local.length)} فایل</span></div>
          ${local.length ? `<div class="panel local-file-panel">${local.map(file => `<div class="local-file-row"><div><strong>${esc(file.name)} ${file.package_guess ? `<span class="chip">${esc(file.package_guess)}</span>` : ''}</strong><small class="path-cell">${esc(file.display_path)}\\${esc(file.relative_path)}</small></div><div>${statusBadge(file.root_availability === 'unavailable' ? 'unavailable' : (file.match_state === 'user_confirmed' ? 'already_present' : 'likely_match'))}<small class="local-root-note">${esc(fmtBytes(file.size_bytes))} · ${esc(file.root_availability === 'unavailable' ? 'دیسک جدا شده؛ دادهٔ پیشین حفظ شد' : `${label(file.provenance)} · اسکن کامل ${fmtDate(file.last_complete_at)}`)}</small></div></div>`).join('')}</div>` : `<div class="empty-block"><strong>فایل محلی مرتبط پیدا نشد</strong>اسکن ناقص یا دیسک جداشده به معنی حذف فایل نیست. از پوشه‌های انتخاب‌شده برای پیوند دستی استفاده کنید.</div>`}
        </div>
      </section>`;
    }).join('');
    $('#game-detail').innerHTML = `<button class="detail-back" data-action="back-games"><span aria-hidden="true">›</span> بازگشت به بازی‌ها</button>
      <div class="detail-header"><div class="detail-title-wrap"><span class="game-spine ${platform.toLowerCase()}">${esc(platform)}</span><div class="detail-title"><h2>${esc(game.display_title || game.canonical_title)}</h2><p>مالکیت: ${esc(label(game.owned?.[0]?.ownership_status || 'user_asserted'))} · ${faNum(game.owned?.length || 0)} ثبت</p></div></div>
       <div class="detail-actions"><button class="button button-outline button-small" data-action="add-candidate" data-release="${esc(releases[0]?.id || '')}">ثبت نامزد</button><button class="button button-quiet button-small" data-action="record-check" data-release="${esc(releases[0]?.id || '')}">ثبت بررسی منبع</button></div></div>
      <div class="detail-meta"><span><strong>پلتفرم</strong>${esc(releases.map(r=>r.platform).filter((v,i,a)=>a.indexOf(v)===i).join('، ')||'نامشخص')}</span><span><strong>عنوان‌های جایگزین</strong>${esc(nameRows.map(n => `${n.value}${n.language ? ` (${n.language})` : ''}`).join('، ') || 'ندارد')}</span><span><strong>شناسه</strong><bdi class="ltr">${esc(ids.join(' / ') || 'ثبت نشده')}</bdi></span><span><strong>منشأ عنوان</strong>${esc(nameRows[0]?.provenance || game.provenance)}</span></div>
      <div class="policy-banner"><span class="policy-symbol">i</span><p>وضعیت پوشش مربوط به هر منبع و دسته است. «بدون نتیجه» فقط زمان همان بررسی را توصیف می‌کند و کامل‌بودن هیچ منبعی را ادعا نمی‌کند.</p></div>
      ${releaseMarkup || `<div class="empty-block"><strong>نسخه‌ای ثبت نشده</strong>یک بازی با پلتفرم و عنوان یا شناسه اضافه کنید.</div>`}`;
  }
  function renderCandidate(item) {
    const observations = [...(item.observations || [])].sort((a,b) => langRank(a.evidence?.page_language) - langRank(b.evidence?.page_language));
    const assessment = item.assessment || {state:'unknown',confidence:'low',evidence:[]};
    const evidence = assessment.evidence || [];
    const sourceParts = observations.map(obs => `<div class="candidate-source"><strong>${esc(obs.source_name)}</strong>${trustBadge(obs.trust_tier)}<span>${esc(obs.enabled ? label(obs.health_state) : 'غیرفعال')}</span><span dir="ltr">${esc(obs.evidence?.page_language || 'زبان صفحه نامشخص')}</span><span dir="ltr">${esc(fmtDate(obs.observed_at))}</span></div>`).join('');
    const links = observations.map(obs => `${obs.observed_uri && safeHref(obs.observed_uri) ? `<a href="${esc(obs.observed_uri)}" target="_blank" rel="noopener noreferrer">مشاهدهٔ صفحهٔ منبع</a>` : ''}${obs.download_uri ? `<span class="uri-text" title="نشانی دریافت دقیق">${esc(obs.download_uri)}</span>` : '<span>نشانی دریافت مستقیم ثبت نشده</span>'}`).join('');
    const downloadButtons = assessment.state === 'incompatible' ? '<span class="quiet-label">به‌دلیل تعارض سازگاری، درخواست دریافت بسته است.</span>' : observations.filter(o => o.download_uri && o.policy?.allow_downloads && o.policy?.review_status === 'reviewed_allowed' && o.trust_tier !== 'blocked' && o.enabled).map(obs => `<button class="button button-primary button-small" data-action="request-download" data-content="${esc(item.id)}" data-observation="${esc(obs.id)}">درخواست تأیید دریافت</button>`).join('');
    const fileMatch = item.local_matches?.length ? `<div class="candidate-facts">${item.local_matches.map(match => `<span>${statusBadge('already_present')}<bdi class="ltr">${esc(match.display_path)}\\${esc(match.relative_path)}</bdi></span>`).join('')}</div>` : '';
    return `<article class="candidate-card"><div class="candidate-head"><div><h4>${esc(item.title)}</h4>${sourceParts || '<div class="candidate-source">منشأ منبع ثبت نشده</div>'}</div>${statusBadge(assessment.state)}</div>
      <div class="candidate-facts"><span><b>دسته</b>${esc(label(item.category))}</span><span><b>نسخه</b><bdi class="ltr">${esc(item.version || 'نامشخص')}</bdi></span><span><b>پلتفرم اعلام‌شده</b>${esc(item.platform || 'نامشخص')}</span><span><b>شناسه</b><bdi class="ltr">${esc(item.title_id || item.product_code || 'نامشخص')}</bdi></span><span><b>ناحیه</b><bdi class="ltr">${esc(item.region || 'نامشخص')}</bdi></span><span><b>اندازه</b><bdi class="ltr">${esc(fmtBytes(item.size_bytes))}</bdi></span><span class="candidate-language"><b>زبان فهرست</b><bdi class="ltr">${esc(item.page_language || observations[0]?.evidence?.page_language || 'نامشخص')}</bdi></span><span class="candidate-language"><b>زبان محتوا / زیرنویس</b><bdi class="ltr">${esc(item.language_evidence || item.language || 'نامشخص')}</bdi></span><span><b>هش اعلام‌شده</b><bdi class="ltr">${esc(item.declared_hash ? `${item.hash_algorithm}: ${item.declared_hash}` : 'ندارد')}</bdi></span></div>
      ${evidence.length ? `<div class="candidate-evidence"><strong>دلیل و نادانسته‌ها · اطمینان ${esc(assessment.confidence || 'کم')}</strong><ul>${evidence.map(ev => `<li>${esc(ev.detail)}</li>`).join('')}</ul></div>` : ''}
      ${fileMatch}
      <div class="candidate-links">${links}</div>
      <div class="candidate-actions"><button class="button button-outline button-small" data-action="assess" data-content="${esc(item.id)}">بازبینی سازگاری</button><button class="button button-quiet button-small" data-action="link-local" data-content="${esc(item.id)}">پیوند به فایل محلی</button>${downloadButtons}</div>
    </article>`;
  }
  function safeHref(value) {
    try { const u = new URL(value); return ['https:','http:'].includes(u.protocol) ? u.href : ''; } catch { return ''; }
  }
  function langRank(value) {
    const v=String(value||'').replace('_','-').toLowerCase();
    if (v === 'fa-ir') return 0;
    if (v === 'fa') return 1;
    const fallback = state.data?.preferences?.fallback_languages || ['en'];
    const index = fallback.findIndex(lang=>String(lang).replace('_','-').toLowerCase()===v);
    return index >= 0 ? index + 2 : v ? fallback.length + 2 : fallback.length + 3;
  }
  function renderSources() {
    if (!state.data) return;
    const sources = state.data.sources || [];
    $('#source-list').innerHTML = sources.length ? sources.map(source => {
      const caps = source.capabilities || {};
      const policy = source.policy || {};
      const last = source.last_check;
      const accessLinks = `${safeHref(source.base_uri) ? `<a href="${esc(source.base_uri)}" target="_blank" rel="noopener noreferrer">صفحهٔ پایه</a>` : ''}${safeHref(source.terms_uri) ? `<a href="${esc(source.terms_uri)}" target="_blank" rel="noopener noreferrer">شرایط دسترسی</a>` : ''}`;
      return `<article class="source-card ${source.trust_tier === 'blocked' ? 'blocked' : ''}"><div>
        <div class="source-card-head"><h3>${esc(source.name)}</h3>${trustBadge(source.trust_tier)}<span class="state-pill ${esc(source.health_state)}">${esc(label(source.health_state))}</span>${source.enabled ? '' : '<span class="chip">غیرفعال</span>'}</div>
        <p>${esc(source.attribution || 'انتساب یا نگه‌دارنده ثبت نشده')} ${source.maintainer ? `· ${esc(source.maintainer)}` : ''}${source.verification_note ? `<br><span class="verification-note">${esc(source.verification_note)}</span>` : ''}</p>
        <div class="source-capabilities">${(caps.platforms || []).map(x => `<span class="chip">${esc(x)}</span>`).join('')}${(caps.categories || []).map(x => `<span class="chip">${esc(label(x))}</span>`).join('')}${(caps.languages || []).map(x => `<span class="chip" dir="ltr">${esc(x)}</span>`).join('')}</div>
        <div class="source-detail-row"><span>خط‌مشی: <bdi>${esc(policy.review_status === 'reviewed_allowed' ? 'بررسی‌شده و مجاز' : policy.review_status === 'blocked' ? 'مسدود' : 'بررسی‌نشده')}</bdi></span><span>دریافت: <bdi>${esc(policy.allow_downloads ? 'مجاز طبق خط‌مشی ثبت‌شده' : 'غیرفعال')}</bdi></span><span>بررسی‌ها: <bdi>${faNum(source.check_count)}</bdi></span><span>آخرین وضعیت: <bdi>${esc(last ? label(last.outcome) : 'ثبت نشده')} · ${esc(last ? fmtDate(last.completed_at) : 'ثبت نشده')}</bdi></span>${accessLinks}</div>
      </div><div class="source-card-actions"><button class="button button-outline button-small" data-action="source-history" data-source="${esc(source.id)}">تاریخچه</button><button class="button button-quiet button-small" data-action="edit-source" data-source="${esc(source.id)}">ویرایش</button></div></article>`;
    }).join('') : `<div class="empty-block"><strong>منبعی در رجیستری نیست</strong>منبعی را که خط‌مشی و انتساب آن را می‌دانید دستی ثبت کنید؛ هیچ آینه یا منبعی از پیش اضافه نشده است.</div>`;
  }
  function renderRoots() {
    if (!state.data) return;
    const roots = state.data.roots || [];
    $('#root-list').innerHTML = roots.length ? roots.map(root => {
      const last = root.last_scan;
      const expanded = state.expandedRoots.has(root.id);
      const files = state.rootFiles.get(root.id) || [];
      return `<article class="root-card"><div class="root-card-head"><div><div class="root-path" title="${esc(root.display_path)}">${esc(root.display_path)}</div><div class="root-card-meta"><span class="state-pill ${esc(root.availability)}">${esc(root.availability === 'unavailable' ? 'دیسک در دسترس نیست' : root.availability === 'scanning' ? 'در حال اسکن' : 'در دسترس')}</span><span>${faNum(root.file_count)} مورد موجود از آخرین اسکن کامل</span><span>انتخاب: ${esc(fmtDate(root.user_selected_at))}</span><span>حجم: <bdi class="ltr">${esc(root.volume_identity || 'نامشخص')}</bdi></span></div></div>
        <span class="quiet-label">${last ? `${esc(label(last.status))} · ${last.status==='running'?`${faNum(last.items_seen)} فایل دیده‌شده`:`${faNum(last.items_seen)} فایل`} · ${esc(fmtDate(last.started_at))}` : 'هنوز اسکن نشده'}</span></div>${last?.reason ? `<small class="scan-reason">${esc(last.reason)}</small>` : ''}
        <div class="root-card-actions"><button class="button button-primary button-small" data-action="scan-root" data-root="${esc(root.id)}" ${root.availability === 'scanning' ? 'disabled' : ''}>اسکن فراداده</button><button class="button button-outline button-small" data-action="toggle-root-files" data-root="${esc(root.id)}">${expanded ? 'بستن فهرست' : 'نمایش فایل‌های ثبت‌شده'}</button>${last?.status === 'running' ? `<button class="button button-danger button-small" data-action="cancel-scan" data-run="${esc(last.id)}">لغو اسکن</button>` : ''}</div>
        ${expanded ? renderRootFiles(files) : ''}</article>`;
    }).join('') : `<div class="empty-block"><strong>پوشه‌ای انتخاب نشده</strong>برای شروع، مسیر یک پوشه را وارد کنید. هیچ دیسکی به‌طور خودکار اسکن نمی‌شود.</div>`;
  }
  function renderRootFiles(files) {
    if (!files.length) return `<div class="empty-state root-file-empty"><h3>فایلی برای نمایش نیست</h3><p>اسکن کامل بعدی فرادادهٔ نام فایل و اندازه را ثبت می‌کند؛ فایل‌های نامرئی یا اسکن ناقص به‌عنوان حذف‌شده گزارش نمی‌شوند.</p></div>`;
    return `<div class="coverage-wrap root-file-wrap"><table class="root-file-table"><thead><tr><th>نام</th><th>نوع احتمالی</th><th>شناسه / نسخه</th><th>اندازه</th><th>وضعیت</th></tr></thead><tbody>${files.slice(0,300).map(file=>`<tr><td class="path-cell">${esc(file.relative_path)}</td><td>${esc(file.package_guess || 'فایل')}</td><td class="ltr">${esc(file.parsed_title_id || '—')} ${esc(file.parsed_version || '')}</td><td dir="ltr">${esc(fmtBytes(file.size_bytes))}</td><td>${esc(label(file.presence_state))}</td></tr>`).join('')}</tbody></table>${files.length>300?`<small class="quiet-label">نمایش ${faNum(300)} از ${faNum(files.length)} مورد؛ از جست‌وجوی بازی برای محدودکردن نتیجه استفاده کنید.</small>`:''}</div>`;
  }
  function renderJobs() {
    if (!state.data) return;
    const jobs = state.data.jobs || [];
    $('#job-list').innerHTML = jobs.length ? jobs.map(job => {
      const snap = job.snapshot || {};
      const item = snap.item || {};
      const dest = snap.destination_path || job.destination_path;
      const stateKey = job.status;
      const percent = job.total_bytes ? Math.min(100, Math.floor(100 * job.progress_bytes / job.total_bytes)) : 0;
      const uncertain = ['unknown','needs_review'].includes(snap.compatibility?.state);
      let actions = '';
      if (job.status === 'awaiting_approval') actions = `<div class="approval-checks"><label class="check-line"><input type="checkbox" data-rights="${esc(job.id)}"><span>تأیید می‌کنم که مجاز به دریافت همین مورد هستم؛ مالکیت بازی به‌تنهایی مجوز این محتوا نیست.</span></label>${uncertain ? `<label class="check-line"><input type="checkbox" data-uncertainty="${esc(job.id)}"><span>شواهد سازگاری و نادانسته‌های این مورد را خوانده‌ام و با عدم‌قطعیت آن موافقم.</span></label>` : ''}</div><div class="job-actions"><button class="button button-primary button-small" data-action="approve-job" data-job="${esc(job.id)}">تأیید همین مورد</button><button class="button button-danger button-small" data-action="reject-job" data-job="${esc(job.id)}">رد درخواست</button></div>`;
      else if (job.status === 'approved') actions = `<div class="job-actions"><button class="button button-primary button-small" data-action="start-job" data-job="${esc(job.id)}">شروع دریافت</button><button class="button button-outline button-small" data-action="cancel-job" data-job="${esc(job.id)}">لغو</button></div>`;
      else if (job.status === 'queued' || job.status === 'downloading') actions = `<progress class="download-progress" value="${percent}" max="100" aria-label="پیشرفت دریافت"></progress><p class="quiet-label">${job.total_bytes ? `${esc(fmtBytes(job.progress_bytes))} از ${esc(fmtBytes(job.total_bytes))}` : esc(fmtBytes(job.progress_bytes))}</p><div class="job-actions"><button class="button button-danger button-small" data-action="cancel-job" data-job="${esc(job.id)}">لغو دریافت</button></div>`;
      else if (job.status === 'completed') actions = `<p class="quiet-label">${esc(job.integrity_state === 'verified' ? 'هش اعلام‌شده با مقدار دریافت‌شده برابر بود.' : 'هش اعلام‌شده‌ای برای مقایسه وجود نداشت. فایل نصب یا باز نشده است.')}</p>`;
      else if (job.error_reason) actions = `<p class="quiet-label">${esc(job.error_reason)}</p>`;
      return `<article class="job-card ${esc(stateKey)}"><div class="job-card-body"><div class="job-heading"><div><h3>${esc(item.title || job.title)}</h3><p class="job-subtitle">${esc(item.game_title || 'بازی')} · ${esc(label(item.category || job.category))} · ${esc(job.source_name)}</p></div>${statusBadge(stateKey)}</div>
        <div class="job-facts"><div class="job-fact"><label>نسخه و شناسه</label><span class="ltr">${esc(item.version || 'نامشخص')} · ${esc(item.title_id || item.product_code || 'شناسه نامشخص')}</span></div><div class="job-fact"><label>سازگاری / اعتماد</label><span>${statusBadge(snap.compatibility?.state || 'unknown')} ${trustBadge(job.trust_tier)}</span></div><div class="job-fact"><label>اندازه / هش</label><span class="ltr">${esc(fmtBytes(item.size_bytes))} · ${esc(item.declared_hash ? `${item.hash_algorithm}:${item.declared_hash}` : 'هش اعلام نشده')}</span></div><div class="job-fact"><label>نشانی دقیق</label><span class="uri-value">${esc(snap.observation?.download_uri || 'ثبت نشده')}</span></div><div class="job-fact"><label>مسیر دقیق مقصد</label><span class="path-value">${esc(dest || 'ثبت نشده')}</span></div><div class="job-fact"><label>تاریخ درخواست</label><span dir="ltr">${esc(fmtDate(job.created_at))}</span></div></div>${actions}
      </div></article>`;
    }).join('') : `<div class="empty-block"><strong>صف دریافت خالی است</strong>برای یک نامزد دقیق، پوشهٔ مقصد و تأیید مستقل لازم است.</div>`;
  }
  function sourceForm(source = null) {
    const caps = source?.capabilities || {};
    const policy = source?.policy || {};
    const check = (list, value) => list.includes(value) ? 'checked' : '';
    const hosts = (policy.allowed_hosts || []).join(', ');
    openModal(`<h2 id="modal-title">${source ? 'ویرایش اطلاعات منبع' : 'ثبت منبع جدید'}</h2><p class="modal-intro">ثبت یک منبع مجوز دسترسی یا ادعای رسمی‌بودن ایجاد نمی‌کند. این نسخه هیچ فهرستی را خودکار واکشی نمی‌کند.</p>
      <form id="source-form" data-source="${esc(source?.id || '')}"><div class="form-grid">
       <div class="form-field"><label>نام قابل نمایش</label><input name="name" required maxlength="160" value="${esc(source?.name || '')}"></div>
       <div class="form-field"><label>نوع منبع</label><select name="source_type"><option value="public_web" ${source?.source_type==='public_web'?'selected':''}>وب عمومی</option><option value="community_catalog" ${source?.source_type==='community_catalog'?'selected':''}>فهرست جامعه</option><option value="local_manifest" ${source?.source_type==='local_manifest'?'selected':''}>مانیفست محلی</option><option value="official_catalog" ${source?.source_type==='official_catalog'?'selected':''}>فهرست رسمی</option></select></div>
       <div class="form-field full"><label>نشانی پایه یا محل مانیفست</label><input class="ltr-field" name="base_uri" value="${esc(source?.base_uri || '')}" placeholder="https://example.org/catalog"><span class="hint">برای دریافت، میزبان نشانی باید با این منبع یا میزبان مجاز دیگری هم‌خوان باشد.</span></div>
       <div class="form-field"><label>سطح اعتماد منبع</label><select name="trust_tier">${['official','maintained_community','unverified','blocked'].map(x=>`<option value="${x}" ${(source?.trust_tier||'unverified')===x?'selected':''}>${esc(label(x))}</option>`).join('')}</select></div>
       <div class="form-field"><label>وضعیت سلامت ثبت‌شده</label><select name="health_state">${['unknown','healthy','limited','unavailable','blocked'].map(x=>`<option value="${x}" ${(source?.health_state||'unknown')===x?'selected':''}>${esc(label(x))}</option>`).join('')}</select></div>
       <div class="form-field"><label>نگه‌دارنده یا مالک شناخته‌شده</label><input name="maintainer" value="${esc(source?.maintainer || '')}"></div>
       <div class="form-field"><label>انتساب و یادداشت اعتماد</label><input name="attribution" value="${esc(source?.attribution || '')}" placeholder="چه کسی منبع را نگه‌داری می‌کند؟"></div>
       <div class="form-field full"><label>مدرک یا دلیل انتخاب سطح اعتماد</label><textarea name="verification_note" placeholder="اختیاری؛ سطح اعتماد و توضیح آن دستی ثبت می‌شوند.">${esc(source?.verification_note || '')}</textarea></div>
       <div class="form-field full"><label>صفحهٔ شرایط / robots / خط‌مشی دسترسی</label><input class="ltr-field" name="terms_uri" value="${esc(source?.terms_uri || '')}" placeholder="https://example.org/terms"></div>
       <div class="form-divider"></div><h3 class="form-section-title">قابلیت‌های اعلام‌شدهٔ منبع</h3>
       <div class="form-field full"><label>پلتفرم‌ها</label><div class="form-row-checks">${['PS4','PS5'].map(x=>`<label><input type="checkbox" name="platforms" value="${x}" ${check(caps.platforms||[],x)}> ${x}</label>`).join('')}</div></div>
       <div class="form-field full"><label>دسته‌های محتوا</label><div class="form-row-checks">${['updates','DLC','subtitles','themes','homebrew'].map(x=>`<label><input type="checkbox" name="categories" value="${x}" ${check(caps.categories||[],x)}> ${esc(label(x))}</label>`).join('')}</div></div>
       <div class="form-field"><label>زبان‌های فهرست با ویرگول جدا</label><input class="ltr-field" name="languages" value="${esc((caps.languages||[]).join(', '))}" placeholder="fa-IR, en"></div>
       <div class="form-field"><label>نوع شناسهٔ قابل جست‌وجو</label><input name="query_types" value="${esc((caps.query_types||[]).join(', '))}" placeholder="title_id, product_code"></div>
       <div class="form-divider"></div><h3 class="form-section-title">سیاست دسترسی که شما بررسی کرده‌اید</h3>
       <div class="form-field"><label>نتیجهٔ بررسی خط‌مشی</label><select name="review_status"><option value="unknown" ${(policy.review_status||'unknown')==='unknown'?'selected':''}>بررسی‌نشده</option><option value="reviewed_allowed" ${policy.review_status==='reviewed_allowed'?'selected':''}>بررسی‌شده و مجاز طبق یادداشت من</option><option value="blocked" ${policy.review_status==='blocked'?'selected':''}>مسدود / دسترسی خودکار ممنوع</option></select></div>
       <div class="form-field"><label>میزبان‌های مجاز برای دریافت، جدا با ویرگول</label><input class="ltr-field" name="allowed_hosts" value="${esc(hosts)}" placeholder="downloads.example.org"><span class="hint">میزبان نشانی پایه به‌طور ضمنی مجاز است؛ نشانی‌های خصوصی و تغییر مسیر به آن‌ها رد می‌شوند.</span></div>
       <div class="form-field"><label>حداکثر اندازهٔ دریافت (بایت)</label><input name="max_download_bytes" type="number" min="0" max="100000000000" value="${esc(policy.max_download_bytes ?? 20000000000)}"></div>
       <div class="form-field"><label>فاصلهٔ حداقل بین درخواست‌های دریافت (ثانیه)</label><input name="request_cooldown_seconds" type="number" min="1" max="86400" value="${esc(policy.request_cooldown_seconds ?? 60)}"></div>
       <div class="form-field"><label>محدودیت / یادداشت نرخ درخواست</label><input name="rate_limit_note" value="${esc(policy.rate_limit_note || '')}" placeholder="بدون واکشی خودکار در این نسخه"></div>
       <div class="form-field full"><div class="form-row-checks"><label><input type="checkbox" name="allow_discovery" ${policy.allow_discovery?'checked':''}> خط‌مشی برای دسترسی آینده بررسی شده است</label><label><input type="checkbox" name="allow_downloads" ${policy.allow_downloads?'checked':''}> دریافت مستقیم طبق همین خط‌مشی مجاز است</label><label><input type="checkbox" name="enabled" ${source?.enabled===false?'':'checked'}> منبع در پوشش نمایش داده شود</label></div><span class="hint">این گزینه‌ها هیچ خزنده‌ای را در نسخهٔ فعلی روشن نمی‌کنند؛ بررسی‌ها و نامزدها دستی ثبت می‌شوند.</span></div>
      </div><div class="modal-actions"><button class="button button-primary" type="submit">ذخیرهٔ منبع</button><button class="button button-outline" type="button" data-action="close-modal">انصراف</button></div></form>`);
  }
  function gameForm() {
    openModal(`<h2 id="modal-title">افزودن بازی به مجموعه</h2><p class="modal-intro">این ثبت، اظهار شما دربارهٔ مجموعه است؛ اطلاعات خرید یا اعتبارنامه لازم نیست.</p>
      <form id="game-form"><div class="form-grid"><div class="form-field"><label>پلتفرم</label><select name="platform" required><option value="PS4">PS4</option><option value="PS5">PS5</option></select></div><div class="form-field"><label>عنوان بازی</label><input name="title" required maxlength="300" placeholder="نام فارسی یا عنوان اصلی"></div>
      <div class="form-field"><label>ناحیه</label><input name="region" placeholder="EU، US، JP"></div><div class="form-field"><label>شناسهٔ عنوان</label><input class="ltr-field" name="title_id" placeholder="CUSA00000 / PPSA00000"></div>
      <div class="form-field"><label>کد محصول</label><input class="ltr-field" name="product_code"></div><div class="form-field"><label>زبان عنوان</label><input class="ltr-field" name="language" placeholder="fa-IR"></div>
      <div class="form-field"><label>تاریخ افزودن به مجموعه</label><input class="ltr-field" name="owned_since" type="date"></div><div class="form-field"><label>زبان‌های محتوا (با ویرگول)</label><input class="ltr-field" name="languages" placeholder="fa, en, ja"></div>
      <div class="form-field full"><label>عنوان‌های جایگزین و آوانویسی (هر خط یک عنوان؛ زبان اختیاری با قالب en|Title یا fa-IR|عنوان)</label><textarea name="aliases" placeholder="en|Original title\nfa-IR|عنوان فارسی یا آوانویسی"></textarea></div>
      <div class="form-field full"><label>یادداشت مالکیت یا منشأ اطلاعات</label><textarea name="notes" placeholder="اختیاری؛ اطلاعات حساب کاربری وارد نکنید."></textarea></div></div><div class="modal-actions"><button class="button button-primary" type="submit">ثبت بازی</button><button class="button button-outline" type="button" data-action="close-modal">انصراف</button></div></form>`);
  }
  function candidateForm(releaseId) {
    const game = state.currentGame;
    const releases = game?.releases || [];
    const sources = state.data?.sources || [];
    const sourceOptions = sources.map(s=>`<option value="${esc(s.id)}">${esc(s.name)} · ${esc(label(s.trust_tier))}</option>`).join('');
    openModal(`<h2 id="modal-title">ثبت نامزد از یک منبع</h2><p class="modal-intro">فقط ادعاهای قابل مشاهده را ثبت کنید. زبان صفحهٔ منبع با زبان زیرنویس/محتوا یکی فرض نمی‌شود.</p>
      <form id="candidate-form"><div class="form-grid"><div class="form-field"><label>نسخهٔ بازی</label><select name="release_id">${releases.map(r=>`<option value="${esc(r.id)}" ${r.id===releaseId?'selected':''}>${esc(r.platform)} · ${esc(r.region||'ناحیه نامشخص')} · ${esc(r.title_id||r.product_code||'بدون شناسه')}</option>`).join('')}</select></div><div class="form-field"><label>منبع</label><select name="source_id" required>${sourceOptions}</select></div>
      <div class="form-field"><label>دسته</label><select name="category">${['updates','DLC','subtitles','themes','homebrew'].map(x=>`<option value="${x}">${esc(label(x))}</option>`).join('')}</select></div><div class="form-field"><label>عنوان فهرست</label><input name="title" required maxlength="300"></div>
      <div class="form-field"><label>پلتفرم اعلام‌شده</label><select name="platform"><option value="">نامشخص</option><option>PS4</option><option>PS5</option></select></div><div class="form-field"><label>شناسهٔ عنوان</label><input class="ltr-field" name="title_id"></div>
      <div class="form-field"><label>کد محصول</label><input class="ltr-field" name="product_code"></div><div class="form-field"><label>ناحیهٔ اعلام‌شده</label><input class="ltr-field" name="region"></div>
      <div class="form-field"><label>زبان صفحهٔ فهرست</label><input class="ltr-field" name="page_language" placeholder="fa-IR"><span class="hint">این مقدار منشأ زبان صفحه است.</span></div><div class="form-field"><label>زبان محتوا / زیرنویس</label><input class="ltr-field" name="language_evidence" placeholder="fa"><span class="hint">فقط در صورت اعلام صریح یا مدرک ثبت شود.</span></div>
      <div class="form-field"><label>نسخه</label><input class="ltr-field" name="version"></div><div class="form-field"><label>اندازه به بایت</label><input class="ltr-field" name="size_bytes" type="number" min="0"></div>
      <div class="form-field"><label>الگوریتم هش</label><select name="hash_algorithm"><option value="">بدون هش</option><option value="sha256">SHA-256</option><option value="sha1">SHA-1</option></select></div><div class="form-field"><label>هش اعلام‌شده</label><input class="ltr-field" name="declared_hash"></div>
      <div class="form-field full"><label>صفحهٔ اصلی فهرست</label><input class="ltr-field" name="observed_uri" placeholder="https://source.example/item"></div><div class="form-field full"><label>نشانی مستقیم دریافت (اختیاری)</label><input class="ltr-field" name="download_uri" placeholder="https://source.example/files/item.pkg"><span class="hint">برای دریافت، HTTPS و میزبان مجاز در خط‌مشی منبع لازم است.</span></div>
      <div class="form-field full"><label>شناسهٔ بیرونی یا یادداشت</label><input class="ltr-field" name="external_id" placeholder="اختیاری"></div></div><div class="modal-actions"><button class="button button-primary" type="submit">ثبت شواهد نامزد</button><button class="button button-outline" type="button" data-action="close-modal">انصراف</button></div></form>`);
  }
  function checkForm(releaseId) {
    const releases = state.currentGame?.releases || [];
    const sources = state.data?.sources || [];
    openModal(`<h2 id="modal-title">ثبت دستی نتیجهٔ بررسی</h2><p class="modal-intro">این نسخه به منبع خودکار وصل نمی‌شود؛ نتیجه و علت را پس از بررسی دستی وارد کنید.</p>
      <form id="check-form"><div class="form-grid"><div class="form-field"><label>نسخهٔ بازی</label><select name="release_id">${releases.map(r=>`<option value="${esc(r.id)}" ${r.id===releaseId?'selected':''}>${esc(r.platform)} · ${esc(r.title_id||r.product_code||'بدون شناسه')}</option>`).join('')}</select></div>
      <div class="form-field"><label>منبع</label><select name="source_id" required>${sources.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('')}</select></div>
      <div class="form-field"><label>دستهٔ بررسی</label><select name="category">${['updates','DLC','subtitles','themes','homebrew'].map(x=>`<option value="${x}">${esc(label(x))}</option>`).join('')}</select></div>
      <div class="form-field"><label>نتیجه</label><select name="outcome">${['checked_found','checked_no_result','unavailable','blocked_by_policy','unsupported','error'].map(x=>`<option value="${x}">${esc(label(x))}</option>`).join('')}</select></div>
      <div class="form-field full"><label>دلیل یا مدرک</label><textarea name="reason" placeholder="مثلاً تاریخ بررسی، کد پاسخ یا علت سیاستی؛ اطلاعات ورود را وارد نکنید."></textarea></div></div><div class="modal-actions"><button class="button button-primary" type="submit">ثبت نتیجه</button><button class="button button-outline" type="button" data-action="close-modal">انصراف</button></div></form>`);
  }
  function downloadRequestForm(contentId, observationId) {
    const roots = state.data?.roots || [];
    const options = roots.filter(r=>r.availability==='available').map(r=>`<option value="${esc(r.display_path)}">${esc(r.display_path)}</option>`).join('');
    openModal(`<h2 id="modal-title">درخواست تأیید دریافت</h2><p class="modal-intro">این مرحله فقط درخواست می‌سازد. قبل از دریافت، نامزد، میزبان و مسیر دقیق را دوباره تأیید می‌کنید.</p>
      <form id="download-request-form" data-content="${esc(contentId)}" data-observation="${esc(observationId)}"><div class="form-grid">
      <div class="form-field full"><label>انتخاب یکی از پوشه‌های ثبت‌شده</label><select id="known-destination"><option value="">انتخاب کنید…</option>${options}<option value="__custom">واردکردن مسیر دیگر</option></select><span class="hint">انتخاب پوشهٔ ثبت‌شده، همان مسیر را به‌عنوان مقصد صریح می‌کند.</span></div>
      <div class="form-field full"><label>مسیر یک پوشهٔ موجود</label><div class="path-entry"><input id="download-destination" name="destination_dir" required class="ltr-field" placeholder="C:\\Users\\You\\Downloads"><button class="button button-outline" type="button" data-action="pick-folder" data-target="download">انتخاب…</button></div></div>
      <div class="form-field full"><div class="policy-banner policy-banner-amber"><span class="policy-symbol">!</span><p>هنوز چیزی دریافت نشده است. مقصد، نام فایل، نسخه، اندازه و هش دقیق در صفحهٔ صف پیش از تأیید نمایش داده می‌شوند.</p></div></div>
      </div><div class="modal-actions"><button class="button button-primary" type="submit">ساخت درخواست بازبینی</button><button class="button button-outline" type="button" data-action="close-modal">انصراف</button></div></form>`);
  }
  async function openGameLocalLink(contentId) {
    try {
      const item = state.currentGame?.releases?.flatMap(r=>r.candidates||[]).find(c=>c.id===contentId);
      const query = item?.title_id || '';
      const results = await api(`/api/local-files?q=${encodeURIComponent(query)}`);
      openModal(`<h2 id="modal-title">پیوند نامزد به فایل محلی</h2><p class="modal-intro">این اقدام کاربر را به‌عنوان منشأ تأیید ثبت می‌کند و وضعیت را «موجود در پوشه» می‌سازد.</p><form id="local-link-form" data-content="${esc(contentId)}"><div class="form-field"><label>جست‌وجوی نام فایل یا شناسه</label><div class="path-entry"><input id="local-file-query" value="${esc(query)}" placeholder="CUSA… یا نام فایل"><button class="button button-outline" type="button" data-action="search-local-files">جست‌وجو</button></div></div><div class="form-field local-link-select"><label>فایل از پوشهٔ انتخاب‌شده</label><select id="local-file-select" name="file_id" required>${localFileOptions(results)}</select></div><div class="modal-actions"><button class="button button-primary" type="submit">تأیید پیوند</button><button class="button button-outline" type="button" data-action="close-modal">انصراف</button></div></form>`);
    } catch (error) { toast(error.message, true); }
  }
  function localFileOptions(results) {
    if (!results.length) return `<option value="">فایلی پیدا نشد؛ ابتدا اسکن کامل پوشه را اجرا کنید.</option>`;
    return `<option value="">یک فایل را انتخاب کنید…</option>${results.map(file=>`<option value="${esc(file.id)}">${esc(file.name)} · ${esc(file.parsed_title_id||'بدون شناسه')} · ${esc(file.display_path)}\\${esc(file.relative_path)}</option>`).join('')}`;
  }
  function renderSettings() {
    if (!state.data) return;
    const prefs = state.data.preferences || {};
    $('#ttl-days').value = prefs.coverage_ttl_days || 30;
    $('#fallback-languages').value = (prefs.fallback_languages || ['en']).join(', ');
    $('#data-location').innerHTML = `<strong>محل پایگاه دادهٔ محلی</strong><code class="ltr">${esc(state.data.data_dir || 'در پوشهٔ دادهٔ کاربر')}</code><p>پایگاه داده نسخهٔ پشتیبان ابری ندارد. برای پشتیبان‌گیری، برنامه را ببندید و فایل پایگاه داده را کپی کنید.</p>`;
  }
  async function showSourceHistory(sourceId) {
    try {
      const rows = await api(`/api/sources/${encodeURIComponent(sourceId)}/checks`);
      const source = state.data.sources.find(s=>s.id===sourceId);
      openModal(`<h2 id="modal-title">تاریخچهٔ بررسی · ${esc(source?.name||'منبع')}</h2><p class="modal-intro">نتیجهٔ هر بررسی مستقل از پوشش دیسک محلی نگه‌داری می‌شود.</p>${rows.length ? `<div class="preview-table-wrap"><table class="preview-table"><thead><tr><th>بازی</th><th>دسته</th><th>نتیجه</th><th>زمان</th><th>دلیل</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.canonical_title)} · ${esc(row.platform)}</td><td>${esc(label(row.category))}</td><td>${statusBadge(row.outcome)}</td><td dir="ltr">${esc(fmtDate(row.completed_at))}</td><td>${esc(row.reason||'—')}</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty-block"><strong>بررسی ثبت نشده</strong>نتیجهٔ دستی بررسی را از صفحهٔ بازی ثبت کنید.</div>`}<div class="modal-actions"><button class="button button-outline" data-action="close-modal">بستن</button></div>`);
    } catch (error) { toast(error.message,true); }
  }
  async function toggleRootFiles(rootId) {
    if (state.expandedRoots.has(rootId)) { state.expandedRoots.delete(rootId); renderRoots(); return; }
    try { const files = await api(`/api/roots/${encodeURIComponent(rootId)}/files`); state.rootFiles.set(rootId,files); state.expandedRoots.add(rootId); renderRoots(); }
    catch (error) { toast(error.message,true); }
  }
  function pollScan(runId) {
    if (state.scanTimers.has(runId)) return;
    const timer = setInterval(async () => {
      try {
        const scan = await api(`/api/scans/${encodeURIComponent(runId)}`);
        const root = state.data?.roots.find(item=>item.id===scan.root_id);
        if (root) { root.last_scan=scan; root.availability=scan.status==='running'?'scanning':scan.status==='unavailable'?'unavailable':'available'; }
        if (state.page === 'roots') renderRoots();
        if (scan.status !== 'running') {
          clearInterval(timer); state.scanTimers.delete(runId);
          await refresh();
          toast(scan.status === 'complete' ? `اسکن کامل شد؛ ${faNum(scan.items_seen)} فایل ثبت شد.` : scan.status === 'unavailable' ? 'پوشه در دسترس نیست؛ اطلاعات اسکن پیشین حفظ شد.' : `اسکن ${label(scan.status)} شد؛ فایل‌های غایب علامت‌گذاری نشدند.`);
        }
      } catch (error) { clearInterval(timer); state.scanTimers.delete(runId); toast(error.message,true); }
    }, 1300);
    state.scanTimers.set(runId,timer);
  }
  function setBusy(form, busy) {
    const button = $('button[type="submit"]',form);
    if (button) { button.disabled = busy; button.dataset.oldText ||= button.textContent; button.textContent = busy ? 'در حال ذخیره…' : button.dataset.oldText; }
  }
  function formObject(form) {
    const out = {};
    const fd = new FormData(form);
    for (const [key,value] of fd.entries()) {
      if (key in out) out[key] = Array.isArray(out[key]) ? [...out[key],value] : [out[key],value];
      else out[key] = value;
    }
    return out;
  }
  function readSourceForm(form) {
    const data = formObject(form);
    data.enabled = form.elements.enabled.checked;
    data.policy = {
      review_status:data.review_status,
      allow_discovery:form.elements.allow_discovery.checked,
      allow_downloads:form.elements.allow_downloads.checked,
      allowed_hosts:String(data.allowed_hosts||'').split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean),
      max_download_bytes:Number(data.max_download_bytes||0),
      request_cooldown_seconds:Number(data.request_cooldown_seconds||60),
      rate_limit_note:data.rate_limit_note||'',
      policy_version:1,
    };
    data.capabilities = {
      platforms:formValues(form,'platforms'), categories:formValues(form,'categories'),
      languages:String(data.languages||'').split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean),
      query_types:String(data.query_types||'').split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean),
    };
    return data;
  }
  function formValues(form,name) { return $$(`input[name="${name}"]:checked`,form).map(input=>input.value); }
  async function handleSubmit(event) {
    const form = event.target;
    const id = form.id;
    if (!['game-form','source-form','candidate-form','check-form','root-form','settings-form','import-preview-form','import-commit-form','download-request-form','local-link-form'].includes(id)) return;
    event.preventDefault();
    setBusy(form,true);
    try {
      if (id === 'game-form') {
        const data = formObject(form); data.languages = String(data.languages||'').split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean);
        const game = await api('/api/games',{method:'POST',body:data});
        closeModal(); await refresh(); toast('بازی به مجموعه افزوده شد.'); await openGame(game.id);
      } else if (id === 'source-form') {
        const data = readSourceForm(form); const sourceId = form.dataset.source;
        await api(sourceId ? `/api/sources/${encodeURIComponent(sourceId)}` : '/api/sources',{method:sourceId?'PUT':'POST',body:data});
        closeModal(); await refresh(); toast(sourceId?'اطلاعات منبع به‌روزرسانی شد.':'منبع ثبت شد.');
      } else if (id === 'candidate-form') {
        const data = formObject(form);
        const result = await api('/api/candidates',{method:'POST',body:data});
        closeModal(); await refresh(); await openGame(state.gameId,false); toast(`نامزد ثبت شد؛ سازگاری: ${label(result.assessment.state)}.`);
      } else if (id === 'check-form') {
        const data = formObject(form); const sourceId = data.source_id; delete data.source_id;
        await api(`/api/sources/${encodeURIComponent(sourceId)}/checks`,{method:'POST',body:data});
        closeModal(); await refresh(); await openGame(state.gameId,false); toast('نتیجهٔ بررسی منبع ثبت شد.');
      } else if (id === 'root-form') {
        const data = formObject(form); await api('/api/roots',{method:'POST',body:data}); form.reset(); await refresh(); toast('پوشه ثبت شد؛ اسکن هنوز آغاز نشده است.');
      } else if (id === 'settings-form') {
        const data = formObject(form); data.fallback_languages=String(data.fallback_languages||'').split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean); data.coverage_ttl_days=Number(data.coverage_ttl_days);
        await api('/api/preferences',{method:'POST',body:data}); await refresh(); toast('تنظیمات ذخیره شد.');
      } else if (id === 'import-preview-form') {
        const file = form.elements.file.files[0]; if (!file) throw new Error('یک فایل انتخاب کنید.');
        const contents = await file.text(); const preview = await api('/api/import/preview',{method:'POST',body:{filename:file.name,contents}});
        showImportPreview(preview);
      } else if (id === 'import-commit-form') {
        const decisions = [];
        $$('.import-action',form).forEach(select => {
          const rowIndex = Number(select.dataset.index);
          const target = $(`.import-target[data-index="${rowIndex}"]`,form);
          decisions.push({index:rowIndex,action:select.value,target_game_id:target?.value||''});
        });
        const result = await api('/api/import/commit',{method:'POST',body:{token:form.dataset.token,decisions}});
        closeModal(); await refresh(); toast(`${faNum(result.added)} بازی افزوده شد؛ ${faNum(result.merged)} ادغام و ${faNum(result.skipped)} ردیف رد شد.`);
        if (state.page === 'games') renderGames();
      } else if (id === 'download-request-form') {
        const data = formObject(form); data.content_item_id=form.dataset.content; data.observation_id=form.dataset.observation;
        const result = await api('/api/jobs',{method:'POST',body:data});
        closeModal(); await refresh(); nav('queue'); toast('درخواست ساخته شد؛ پیش از دریافت آن را مرور و تأیید کنید.');
      } else if (id === 'local-link-form') {
        const data = formObject(form); await api(`/api/candidates/${encodeURIComponent(form.dataset.content)}/link-local`,{method:'POST',body:data});
        closeModal(); await refresh(); await openGame(state.gameId,false); toast('پیوند محلی با منشأ تأیید کاربر ثبت شد.');
      }
    } catch (error) { toast(error.message,true); }
    finally { if (form.isConnected) setBusy(form,false); }
  }
  function showImportStart() {
    openModal(`<h2 id="modal-title">پیش‌نمایش ورود بازی‌ها</h2><p class="modal-intro">قالب CSV ستون‌های platform و title یا شناسه را می‌پذیرد؛ JSON باید schema_version برابر 1 و games داشته باشد. ردیف‌های تکراری یا مبهم پیش از ذخیره علامت‌گذاری می‌شوند.</p><form id="import-preview-form"><div class="form-field"><label>فایل UTF-8 CSV یا JSON</label><input type="file" name="file" accept=".csv,.json" required></div><p class="hint">فرمت مستند در فایل README این مخزن آمده است؛ فایل حداکثر ۲ مگابایت و ۲۰۰۰ ردیف باشد.</p><div class="modal-actions"><button class="button button-primary" type="submit">ساخت پیش‌نمایش</button><button class="button button-outline" type="button" data-action="close-modal">انصراف</button></div></form>`);
  }
  function showImportPreview(preview) {
    const count = {ready:0,duplicate:0,ambiguous:0,invalid:0};
    preview.rows.forEach(row=>count[row.status]++);
    const rows = preview.rows.map(row => {
      const matches = row.matches || [];
      const options = row.status === 'invalid' ? `<option value="skip" selected>رد ردیف نامعتبر</option>` : [
        row.status === 'ambiguous' ? `<option value="review" selected>نیازمند تصمیم؛ فعلاً رد شود</option>` : '',
        `<option value="new" ${row.default_action==='new'?'selected':''}>افزودن به‌عنوان بازی جدا</option>`,
        matches.some(m=>m.game_id) ? `<option value="merge">ادغام با بازی انتخابی</option>` : '',
        `<option value="skip" ${row.default_action==='skip'?'selected':''}>رد / نگه‌داری بدون تغییر</option>`,
      ].join('');
      const targetOptions = matches.filter(m=>m.game_id).map(m=>`<option value="${esc(m.game_id)}">${esc(m.title)} · ${esc(m.kind==='exact_identifier'?'شناسه دقیق':'عنوان مشابه')}</option>`).join('');
      const warnings = [row.error, ...matches.map(m=>`${m.kind==='exact_identifier'?'شناسهٔ تکراری':m.kind==='duplicate_in_file'?'ردیف همسان در فایل':'عنوان مشابه'}: ${m.title}`)].filter(Boolean);
      return `<tr><td>${faNum(row.line)}</td><td>${esc(row.record.title||row.record.title_id||row.record.product_code||'—')}</td><td>${esc(row.record.platform||'نامشخص')}<br><bdi class="ltr">${esc(row.record.title_id||row.record.product_code||'—')}</bdi>${warnings.length?`<span class="review-match">${warnings.map(esc).join('<br>')}</span>`:''}</td><td><select class="import-action" data-index="${row.index}">${options}</select>${targetOptions?`<select class="import-target" data-index="${row.index}" aria-label="بازی مقصد" disabled><option value="">انتخاب بازی مقصد…</option>${targetOptions}</select>`:''}</td></tr>`;
    }).join('');
    openModal(`<h2 id="modal-title">بازبینی پیش‌نمایش · ${esc(preview.filename)}</h2><p class="import-summary">${faNum(preview.rows.length)} ردیف · آماده: ${faNum(count.ready)} · تکراری: ${faNum(count.duplicate)} · مبهم: ${faNum(count.ambiguous)} · نامعتبر: ${faNum(count.invalid)}. هر ردیف باید جداگانه افزوده، ادغام یا رد شود.</p>
      <form id="import-commit-form" data-token="${esc(preview.token)}"><div class="preview-table-wrap"><table class="preview-table"><thead><tr><th>ردیف</th><th>عنوان</th><th>هویت و هشدار</th><th>تصمیم</th></tr></thead><tbody>${rows}</tbody></table></div><div class="modal-actions"><button class="button button-primary" type="submit">اعمال تصمیم‌ها</button><button class="button button-outline" type="button" data-action="close-modal">لغو</button></div></form>`);
  }
  function updateImportTargets(form) {
    $$('.import-action',form).forEach(select=>{
      const target = $(`.import-target[data-index="${select.dataset.index}"]`,form);
      if (target) { target.disabled = select.value !== 'merge'; target.required = select.value === 'merge'; }
    });
  }
  document.addEventListener('submit', handleSubmit);
  document.addEventListener('change', event => {
    const node = event.target;
    if (node.matches('.import-action')) updateImportTargets(node.form);
    if (node.id === 'known-destination') $('#download-destination').value = node.value && node.value !== '__custom' ? node.value : '';
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('button,[data-game]');
    if (!button) return;
    if (button.matches('.nav-item[data-page]')) { nav(button.dataset.page); return; }
    if (button.dataset.go) { nav(button.dataset.go); return; }
    if (button.dataset.game) { await openGame(button.dataset.game); return; }
    if (button.dataset.platform) {
      state.platformFilter = button.dataset.platform;
      $$('#platform-filter button').forEach(b=>b.classList.toggle('selected',b===button)); renderGames(); return;
    }
    const action = button.dataset.action;
    try {
      if (action === 'add-game') { gameForm(); return; }
      if (action === 'close-modal') { closeModal(); return; }
      if (action === 'back-games') { nav('games'); return; }
      if (action === 'add-candidate') { if (!state.currentGame?.releases?.length) throw new Error('بازی نسخه‌ای ندارد.'); if (!state.data.sources.length) throw new Error('پیش از ثبت نامزد، یک منبع در رجیستری اضافه کنید.'); candidateForm(button.dataset.release); return; }
      if (action === 'record-check') { if (!state.data.sources.length) throw new Error('پیش از ثبت نتیجه، منبعی اضافه کنید.'); checkForm(button.dataset.release); return; }
      if (action === 'edit-source') { const source = state.data.sources.find(s=>s.id===button.dataset.source); if (source) sourceForm(source); return; }
      if (action === 'source-history') { await showSourceHistory(button.dataset.source); return; }
      if (action === 'search-local-files') {
        const results = await api(`/api/local-files?q=${encodeURIComponent($('#local-file-query')?.value || '')}`);
        $('#local-file-select').innerHTML = localFileOptions(results);
        return;
      }
      if (action === 'pick-folder') {
        const field = button.dataset.target === 'root' ? $('#root-path') : $('#download-destination');
        const result = await api('/api/pick-folder',{method:'POST',body:{initial_dir:field?.value||''}});
        if (result.path && field) field.value = result.path;
        return;
      }
      if (action === 'toggle-root-files') { await toggleRootFiles(button.dataset.root); return; }
      if (action === 'scan-root') {
        const run = await api(`/api/roots/${encodeURIComponent(button.dataset.root)}/scan`,{method:'POST',body:{}});
        await refresh(); if (run.status==='running') { pollScan(run.id); toast('اسکن فقط فراداده آغاز شد؛ هیچ فایلی تغییر نمی‌کند.'); }
        else toast(run.reason || 'پوشه در دسترس نیست.'); return;
      }
      if (action === 'cancel-scan') { await api(`/api/scans/${encodeURIComponent(button.dataset.run)}/cancel`,{method:'POST',body:{}}); toast('درخواست لغو ثبت شد؛ اسکن ناقص فایل‌ها را حذف نمی‌کند.'); return; }
      if (action === 'assess') { await api(`/api/candidates/${encodeURIComponent(button.dataset.content)}/assess`,{method:'POST',body:{}}); await refresh(); await openGame(state.gameId,false); toast('ارزیابی شواهد به‌روزرسانی شد.'); return; }
      if (action === 'link-local') { await openGameLocalLink(button.dataset.content); return; }
      if (action === 'request-download') { downloadRequestForm(button.dataset.content,button.dataset.observation); return; }
      if (action === 'approve-job') {
        const rights = $(`[data-rights="${CSS.escape(button.dataset.job)}"]`);
        const uncertainty = $(`[data-uncertainty="${CSS.escape(button.dataset.job)}"]`);
        await api(`/api/jobs/${encodeURIComponent(button.dataset.job)}/approve`,{method:'POST',body:{rights_confirmed:!!rights?.checked,uncertainty_ack:!!uncertainty?.checked}});
        await refresh(); toast('تصمیم شما برای همین جزئیات ثبت شد؛ دریافت هنوز آغاز نشده است.'); return;
      }
      if (action === 'reject-job') { await api(`/api/jobs/${encodeURIComponent(button.dataset.job)}/reject`,{method:'POST',body:{}}); await refresh(); toast('درخواست دریافت رد شد.'); return; }
      if (action === 'start-job') { await api(`/api/jobs/${encodeURIComponent(button.dataset.job)}/start`,{method:'POST',body:{}}); await refresh(); toast('دریافت مجاز آغاز شد.'); const timer=setInterval(async()=>{await refresh();const j=state.data.jobs.find(x=>x.id===button.dataset.job);if(!j||!['queued','downloading'].includes(j.status)){clearInterval(timer);}},1400); return; }
      if (action === 'cancel-job') { await api(`/api/jobs/${encodeURIComponent(button.dataset.job)}/cancel`,{method:'POST',body:{}}); await refresh(); toast('لغو دریافت درخواست شد.'); return; }
    } catch (error) { toast(error.message,true); }
  });
  $('#add-game-open').addEventListener('click',gameForm);
  $('#add-game-open-2').addEventListener('click',gameForm);
  $('#import-open').addEventListener('click',showImportStart);
  $('#import-open-2').addEventListener('click',showImportStart);
  $('#import-file').addEventListener('change',event=>{ if(event.target.files.length) { const file=event.target.files[0]; showImportStart(); const input=$('input[type=file]',$('#modal-content')); const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files; } });
  $('#source-add-open').addEventListener('click',()=>sourceForm());
  $('#refresh-roots').addEventListener('click',async()=>{await refresh();toast('وضعیت پوشه‌های ثبت‌شده تازه شد.');});
  $('#global-search').addEventListener('input',event=>{state.search=event.target.value;if(state.page==='games')renderGames();});
  $('#global-search').addEventListener('keydown',event=>{if(event.key==='Enter'){nav('games');$('#global-search').blur();}});
  document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){event.preventDefault();$('#global-search').focus();}});
  document.addEventListener('keydown',event=>{const game=event.target.closest('[data-game]');if(game&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openGame(game.dataset.game);}});
  $('#modal').addEventListener('click',event=>{if(event.target===$('#modal'))closeModal();});
  $('#modal').addEventListener('close',()=>{$('#modal-content').innerHTML='';});
  renderNavCounts();
  api('/api/bootstrap').then(data=>{state.data=data;renderNavCounts();renderOverview();}).catch(error=>toast(error.message,true));
})();
