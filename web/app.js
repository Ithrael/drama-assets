const $ = (id) => document.getElementById(id);
const icons = {
  screen: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 17v4m-5 0h10"/>',
  people: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M15 3.13a4 4 0 0 1 0 7.75"/><circle cx="9" cy="7" r="4"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
  settings: '<path d="m9 3-1 3-3 1-2 3 2 2-1 3 2 3 3-1 2 3h3l1-3 3-1 2-3-2-2 1-3-2-3-3 1-2-3Z"/><circle cx="11" cy="11" r="3"/>',
  sliders: '<path d="M4 7h5m5 0h6M4 17h10m5 0h1"/><circle cx="11.5" cy="7" r="2.5"/><circle cx="16.5" cy="17" r="2.5"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 3v18M17 3v18M3 8h4m-4 8h4M17 8h4m-4 8h4"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  sparkles: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v5m-2.5-2.5h5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.2"/>',
  scan: '<path d="M8 3H4a1 1 0 0 0-1 1v4m13-5h4a1 1 0 0 1 1 1v4M3 16v4a1 1 0 0 0 1 1h4m8 0h4a1 1 0 0 0 1-1v-4M7 12h10"/><circle cx="12" cy="9" r="2"/><path d="M8 17a4 4 0 0 1 8 0"/>',
  grid: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>',
  portrait: '<rect x="4" y="2" width="16" height="20" rx="2"/><circle cx="12" cy="9" r="3"/><path d="M7 20v-2a5 5 0 0 1 10 0v2"/>',
  person: '<circle cx="12" cy="4" r="2"/><path d="m7 20 2-7V9a3 3 0 0 1 6 0v4l2 7M9 10l-4 4m10-4 4 4M12 14v7"/>',
  views: '<rect x="2" y="4" width="6" height="16" rx="1"/><rect x="9" y="4" width="6" height="16" rx="1"/><rect x="16" y="4" width="6" height="16" rx="1"/>',
  sheet: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 15h18M14 3v12M7 18h2m7-11h2m-2 4h2"/><circle cx="8.5" cy="7" r="1.5"/><path d="M6 13v-1a2.5 2.5 0 0 1 5 0v1"/>',
  play: '<path d="m9 5 10 7-10 7V5Z"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="m6 6 12 12M6 18 18 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5M5.5 7a7.5 7.5 0 0 1 12.4-2L20 8M4 16l2.1 3A7.5 7.5 0 0 0 18.5 17"/>'
};
function icon(name) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.sheet}</svg>`; }
function hydrateIcons(root = document) { root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); }); }
function escapeText(value) { const el = document.createElement('span'); el.textContent = value; return el.innerHTML.replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
// All displayed images come from local API paths, never model-provided URLs.
function safeUrl(value) { return /^(\/media\/[a-f0-9]{32}\/|\/examples\/)/.test(value) ? value : ''; }
const types = [
  { id: 'expressions', name: '情绪九宫格', detail: '平静、喜悦、悲伤等 9 种常见情绪', icon: 'grid' },
  { id: 'half', name: '上半身图', detail: '五官、发型与上装细节', icon: 'portrait' },
  { id: 'full', name: '全身图', detail: '完整造型、服饰与身形比例', icon: 'person' },
  { id: 'views', name: '正侧背三视图', detail: '正面、侧面、背面一致呈现', icon: 'views' },
  { id: 'sheet', name: '角色设定图', detail: '形象、服饰、配饰与配色档案', icon: 'sheet' }
];
let project = null, selected = null, tab = 'expressions', pollTimer, toastTimer, uploading = false;
let autoAnalyze = false;
let configuration = {};
const initialStage = $('asset-stage').innerHTML;
$('asset-options').innerHTML = types.map(type => `<label class="asset-option"><span class="option-icon">${icon(type.icon)}</span><span class="option-copy"><strong>${type.name}</strong><small>${type.detail}</small></span><input type="checkbox" value="${type.id}" checked aria-label="生成${type.name}"></label>`).join('');
hydrateIcons();
function busy() { return uploading || ['extracting', 'analyzing', 'generating'].includes(project?.status); }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 4500); }
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '请求失败，请检查输入后重试');
  return payload;
}
function post(path, data) { return api(path, { method: 'POST', ...(data ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : {}) }); }
function checkedKinds() { return [...$('asset-options').querySelectorAll('input:checked')].map(el => el.value); }
function time(seconds) { return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`; }
function activeCharacter() { return project?.characters?.find(c => c.id === selected); }
function hasModel() { return configuration.execution_mode === 'conversation' || (configuration.has_key && configuration.vision_model); }
function settingsMode() { const form = $('settings-form'); const external = form.elements.execution_mode.value === 'api'; $('api-settings-fields').hidden = !external; for (const key of ['base_url', 'vision_model', 'image_model']) form.elements[key].required = external; }
function showSettings() { const form = $('settings-form'); for (const key of ['base_url', 'vision_model', 'image_model']) form.elements[key].value = configuration[key] || ''; form.elements.execution_mode.value = configuration.execution_mode || 'conversation'; form.elements.api_key.value = ''; form.elements.api_key.placeholder = configuration.has_key ? '已配置，留空保留原 Key' : '输入 API Key'; settingsMode(); $('settings-error').hidden = true; $('settings-dialog').showModal(); }
async function refreshSettings() { configuration = await api('/api/settings'); const current = configuration.execution_mode === 'conversation'; const connected = current || (configuration.has_key && configuration.vision_model && configuration.image_model); $('connection').innerHTML = `<i></i> ${current ? '当前对话模型' : connected ? 'API 已配置' : 'API 未配置'}`; $('connection').classList.toggle('connected', !!connected); }
function preview(url, title) { $('preview-image').src = safeUrl(url); $('preview-title').textContent = title; $('preview-download').href = safeUrl(url); $('preview-download').download = title + '.png'; $('preview-dialog').showModal(); }
function render() {
  const loading = busy(), person = activeCharacter();
  $('character-count').textContent = project?.characters?.length || 0;
  $('character-empty').hidden = !!project?.characters?.length;
  $('characters').hidden = !project?.characters?.length;
  $('characters').innerHTML = (project?.characters || []).map(c => `<button class="character-card ${c.id === selected ? 'selected' : ''}" data-character="${c.id}" aria-pressed="${c.id === selected}"><img src="${safeUrl(c.reference)}" alt="${escapeText(c.name)}"><span><strong>${escapeText(c.name)}</strong><small>角色 ${escapeText(c.id)} · ${Object.keys(c.assets).length} 项资产</small></span>${c.id === selected ? '<span class="selected-mark">✓</span>' : ''}</button>`).join('');
  $('analyze-button').disabled = loading || !project || project.demo || !project.frames.length || project.characters.some(c => Object.keys(c.assets).length);
  $('generate-button').disabled = loading || !person || project?.demo || !checkedKinds().length;
  $('download-button').disabled = loading || !project || project.demo || !project.characters.length;
  $('dashboard-button').disabled = loading || !project || project.demo || !project.characters.length;
  $('generation-scope').hidden = !project?.characters?.length || project.demo;
  const pending = project?.pending_request;
  $('conversation-request').hidden = !pending;
  $('conversation-prompt').value = pending?.prompt || '';
  $('demo-button').disabled = loading;
  $('replace-video').disabled = loading;
  document.body.classList.toggle('busy', loading);
  $('status-bar').hidden = !loading;
  $('status-text').textContent = uploading ? '正在上传视频，请稍候' : project?.message || '';
  $('progress-label').textContent = uploading || project?.status === 'analyzing' ? '' : `${project?.progress || 0}%`;
  $('progress-fill').style.width = `${project?.progress || 0}%`;
  $('error-box').hidden = !project?.error;
  $('error-box').textContent = project?.error || '';
  $('step-upload').className = 'step ' + (project ? 'done' : 'current');
  $('step-analyze').className = 'step ' + (project?.characters?.length ? 'done' : project ? 'current' : '');
  $('step-assets').className = 'step ' + (project?.characters?.length ? 'current' : '');
  $('assets-subtitle').textContent = person ? `${person.name} · ${project.demo ? '已有样片，未生成项可在真实项目中制作' : '基于角色参考图，保持视觉一致性'}` : '从银幕中的一瞬，到完整的角色。';
  $('asset-total').textContent = person ? `已完成 ${Object.keys(person.assets).length} / 5 类资产` : '5 类资产 · 完整角色档案';
  $('asset-tabs').innerHTML = types.map(type => `<button class="asset-tab ${tab === type.id ? 'selected' : ''}" data-tab="${type.id}" aria-pressed="${tab === type.id}">${type.name}${person?.assets[type.id] ? '<i class="tab-dot"></i>' : ''}</button>`).join('');
  if (!person) {
    if (!$('asset-stage').querySelector('.stage-empty')) { $('asset-stage').innerHTML = initialStage; hydrateIcons($('asset-stage')); }
  } else if (person.assets[tab]) {
    const a = person.assets[tab];
    $('asset-stage').innerHTML = `<img class="asset-image" src="${safeUrl(a.url)}" alt="${escapeText(person.name + ' · ' + a.label)}" title="点击放大预览" tabindex="0" role="button" data-preview="${safeUrl(a.url)}">`;
  } else {
    const type = types.find(t => t.id === tab);
    $('asset-stage').innerHTML = `<div class="result-empty"><span>${icon(type.icon)}</span><h3>${project.demo ? '样片尚未包含' : '等待生成'}${type.name}</h3><p>${project.demo ? '当前展示项目已有的三视图样片。上传你的视频，通过 Skill 即可制作完整的五类人物资产。' : '选择左侧需要的资产类型，点击「生成资产」。'}</p>${project.demo ? '<button class="button primary" id="demo-upload">上传我的视频</button>' : ''}</div>`;
  }
  $('frame-section').hidden = !project?.frames?.length;
  if (project?.frames?.length) {
    $('frames-count').textContent = `${project.frames.length} 帧`;
    $('frames').innerHTML = project.frames.map(f => `<div class="frame" tabindex="0" role="button" aria-label="预览 ${time(f.seconds)} 关键帧" data-frame="${f.index}"><img src="${safeUrl(f.url)}" alt="${time(f.seconds)} 关键帧" loading="lazy"><span>${time(f.seconds)}</span></div>`).join('');
  }
  $('kind-count').textContent = `${checkedKinds().length} 项`;
}
async function loadProject(id) {
  clearTimeout(pollTimer);
  project = await api('/api/projects/' + id);
  if (!project.characters.some(c => c.id === selected)) selected = project.characters[0]?.id || null;
  localStorage.setItem('mujian-project', id);
  $('dropzone').hidden = true;
  $('video-preview').hidden = false;
  const url = safeUrl(project.video_url);
  if ($('source-video').getAttribute('src') !== url) $('source-video').src = url;
  $('video-name').textContent = project.name;
  $('video-meta').textContent = project.metadata ? `${time(project.metadata.duration)} · ${project.metadata.width} × ${project.metadata.height}${project.metadata.has_audio ? '' : ' · 无音轨'}` : `${(project.size / 1024 / 1024).toFixed(1)} MB · 正在读取`;
  render();
  if (['extracting', 'analyzing', 'generating', 'awaiting_analysis', 'awaiting_generation'].includes(project.status)) pollTimer = setTimeout(() => loadProject(id).catch(handlePollError), 2000);
  else if (autoAnalyze && project.status === 'frames_ready' && !project.error && hasModel()) { autoAnalyze = false; await analyze(); }
  else if (project.status === 'frames_ready' && !project.error && !hasModel()) toast('关键帧已提取，选择当前对话模式或配置 API 后即可分析');
  else if (project.status === 'ready') pollTimer = setTimeout(() => loadProject(id).catch(handlePollError), 5000);
}
function handlePollError(error) { toast('读取进度失败：' + error.message); pollTimer = setTimeout(() => loadProject(project.id).catch(handlePollError), 5000); }
async function upload(file) {
  if (!file || busy()) return;
  if (!/\.(mp4|mov|webm|mkv|m4v)$/i.test(file.name)) return toast('请选择 MP4、MOV、WebM、MKV 或 M4V 视频');
  if (file.size > 1024 ** 3) return toast('请选择 1 GB 以内的视频');
  if (!file.size) return toast('视频文件为空');
  clearTimeout(pollTimer); uploading = true; autoAnalyze = true; render();
  const data = new FormData(); data.append('file', file);
  try { const result = await api('/api/upload', { method: 'POST', body: data }); selected = null; project = null; uploading = false; await loadProject(result.id); }
  catch (error) { toast(error.message); }
  finally { uploading = false; $('video-input').value = ''; render(); }
}
async function analyze() {
  if (!hasModel()) { showSettings(); return; }
  try { await post(`/api/projects/${project.id}/analyze`); await loadProject(project.id); }
  catch (error) { toast(error.message); }
}
async function demo() {
  if (busy()) return;
  try { clearTimeout(pollTimer); project = await api('/api/demo'); selected = project.characters[0]?.id; tab = 'views'; $('dropzone').hidden = false; $('video-preview').hidden = true; render(); toast('正在查看本地已有样片，其他资产类型尚未生成'); }
  catch (error) { toast(error.message); }
}
$('dropzone').addEventListener('click', () => { if (!busy()) $('video-input').click(); });
$('dropzone').addEventListener('keydown', e => { if (['Enter', ' '].includes(e.key)) { e.preventDefault(); if (!busy()) $('video-input').click(); } });
$('video-input').addEventListener('change', e => upload(e.target.files[0]));
$('replace-video').addEventListener('click', () => $('video-input').click());
for (const event of ['dragover', 'dragenter']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.add('dragging'); });
for (const event of ['dragleave', 'drop']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.remove('dragging'); });
$('dropzone').addEventListener('drop', e => upload(e.dataTransfer.files[0]));
$('asset-options').addEventListener('change', render);
$('analyze-button').addEventListener('click', analyze);
$('generate-button').addEventListener('click', async () => {
  if (configuration.execution_mode !== 'conversation' && (!configuration.has_key || !configuration.image_model)) { showSettings(); return; }
  const kinds = checkedKinds();
  const ids = $('all-characters').checked ? project.characters.map(c => c.id) : [selected];
  try { await post(`/api/projects/${project.id}/generate`, { character_ids: ids, kinds }); await loadProject(project.id); }
  catch (error) { toast(error.message); }
});
$('download-button').addEventListener('click', () => { if (project && !project.demo) window.location.href = `/api/projects/${project.id}/download`; });
$('dashboard-button').addEventListener('click', () => { if (project && !project.demo) window.open(`/api/projects/${project.id}/dashboard`, '_blank', 'noopener'); });
$('copy-prompt').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('conversation-prompt').value); toast('已复制，粘贴到当前 Codex 对话即可'); } catch { $('conversation-prompt').focus(); $('conversation-prompt').select(); toast('请复制已选中的 Skill 指令'); } });
$('settings-form').elements.execution_mode.addEventListener('change', settingsMode);
$('demo-button').addEventListener('click', demo);
$('asset-tabs').addEventListener('click', e => { const button = e.target.closest('[data-tab]'); if (button) { tab = button.dataset.tab; render(); } });
$('characters').addEventListener('click', e => { const button = e.target.closest('[data-character]'); if (button) { selected = button.dataset.character; render(); } });
$('asset-stage').addEventListener('click', e => { if (e.target.closest('#stage-demo')) demo(); if (e.target.closest('#demo-upload')) $('video-input').click(); const img = e.target.closest('[data-preview]'); if (img) preview(img.dataset.preview, activeCharacter().name + ' · ' + types.find(t => t.id === tab).name); });
$('asset-stage').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.dataset.preview) e.target.click(); });
$('frames').addEventListener('click', e => { const frame = e.target.closest('[data-frame]'); if (frame) { const f = project.frames[Number(frame.dataset.frame)]; preview(f.url, '原片参考帧 ' + time(f.seconds)); } });
$('frames').addEventListener('keydown', e => { if (e.key === 'Enter') e.target.click(); });
for (const id of ['settings-nav', 'settings-top']) $(id).addEventListener('click', showSettings);
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(button.dataset.close).close()));
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); } }));
$('settings-form').addEventListener('submit', async e => {
  e.preventDefault(); const button = e.submitter; button.disabled = true;
  try { await post('/api/settings', Object.fromEntries(new FormData(e.target))); e.target.elements.api_key.value = ''; await refreshSettings(); $('settings-dialog').close(); toast('模型设置已保存'); render(); }
  catch (error) { $('settings-error').textContent = error.message; $('settings-error').hidden = false; }
  finally { button.disabled = false; }
});
$('projects-nav').addEventListener('click', async () => {
  try { const items = await api('/api/projects'); $('project-list').innerHTML = items.length ? items.map(p => `<button class="project-row" data-project="${p.id}"><span><strong>${escapeText(p.name)}</strong><small>${p.characters} 位角色</small></span>${icon('arrow')}</button>`).join('') : '<p class="form-note">还没有项目，上传一段视频即可开始。</p>'; $('projects-dialog').showModal(); }
  catch (error) { toast(error.message); }
});
$('project-list').addEventListener('click', async e => { const row = e.target.closest('[data-project]'); if (!row) return; if (busy()) return toast('请等待当前任务完成'); try { autoAnalyze = false; await loadProject(row.dataset.project); $('projects-dialog').close(); } catch (error) { toast(error.message); } });
$('workspace-nav').addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
async function init() {
  render();
  try { await refreshSettings(); const last = localStorage.getItem('mujian-project'); if (last) await loadProject(last); }
  catch (error) { toast('工作台加载失败：' + error.message); }
}
init();
