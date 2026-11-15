"""将项目资产生成无需服务器、可离线打开的展示大屏。"""
import base64
from html import escape
from pathlib import Path


def write_dashboard(job, folder, kinds):
    folder = Path(folder)
    people = job.get("characters", [])
    total = len(people) * len(kinds)
    completed = sum(1 for c in people for k, a in c["assets"].items()
                    if k in kinds and (folder / Path(a["url"]).name).is_file())

    def image(url):
        name = Path(url).name
        path = folder / name
        if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            return ""
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/" + path.suffix[1:].lower()
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()

    cards = []
    order = ["full", "half", "expressions", "views", "sheet"]
    for character in people:
        tiles = []
        for kind in order:
            label = kinds[kind][0]
            asset = character["assets"].get(kind)
            src = image(asset["url"]) if asset else ""
            body = (f'<button class="image-button" data-title="{escape(character["name"] + " · " + label, quote=True)}">'
                    f'<img src="{src}" alt="{escape(label, quote=True)}" loading="lazy"></button>' if src else
                    '<div class="missing"><span>＋</span><p>尚未生成</p></div>')
            tiles.append(f'<article class="asset" data-kind="{kind}"><div class="asset-label">{escape(label)}'
                         f'<span>{"已生成" if src else "待生成"}</span></div>{body}</article>')
        count = sum(1 for k, a in character["assets"].items() if k in kinds and (folder / Path(a["url"]).name).is_file())
        reference = image(character.get("reference", ""))
        portrait = f'<img class="reference" src="{reference}" alt="原片参考" title="原片裁切参考">' if reference else ''
        cards.append(f'<section class="character" data-search="{escape(character["name"] + " " + character["description"], quote=True)}">'
                     f'<div class="character-heading"><div>{portrait}<span class="character-id">{escape(character["id"])}</span>'
                     f'<h2>{escape(character["name"])}</h2><span class="completion">{count} / 5 类资产</span></div>'
                     f'<p>{escape(character["description"])}</p></div><div class="asset-grid">{"".join(tiles)}</div></section>')
    filters = '<button class="filter active" data-filter="all">全部资产</button>' + ''.join(
        f'<button class="filter" data-filter="{kind}">{escape(kinds[kind][0])}</button>' for kind in order)
    metadata = job.get("metadata", {})
    duration = metadata.get("duration", 0)
    minutes, seconds = divmod(int(duration), 60)
    content = TEMPLATE.replace("{{TITLE}}", escape(job["name"])).replace("{{CHARACTERS}}", str(len(people)))
    content = content.replace("{{COMPLETED}}", str(completed)).replace("{{TOTAL}}", str(total))
    content = content.replace("{{PROGRESS}}", str(round(completed / total * 100) if total else 0))
    content = content.replace("{{DURATION}}", f"{minutes:02d}:{seconds:02d}")
    content = content.replace("{{FILTERS}}", filters).replace("{{CARDS}}", ''.join(cards))
    content = content.replace("{{STATE}}", "全部资产已就绪" if total and completed == total else "部分资产尚未生成")
    target = folder / "dashboard.html"
    temporary = target.with_suffix(".html.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(target)
    return target


TEMPLATE = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>幕间 · {{TITLE}} · 角色资产大屏</title>
<style>
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#181c25;color:#e8ecf5}*{box-sizing:border-box}body{margin:0}button,input{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid #93b4ff;outline-offset:4px}[hidden]{display:none!important}header{border-bottom:1px solid #313744;padding:21px 38px;display:flex;align-items:center;gap:17px}.logo{font-weight:650;font-size:22px;letter-spacing:4px}.header-divider{height:19px;width:1px;background:#3b4352}.workspace{color:#8b96ac;font-size:12px}.header-actions{margin-left:auto;display:flex;gap:10px}.header-actions button{background:#262d3b;border:1px solid #3b4456;border-radius:6px;padding:8px 12px;color:#bac6dc;font-size:11px}main{padding:38px;max-width:2400px;margin:auto}.intro{display:flex;justify-content:space-between;align-items:flex-end;gap:30px;margin-bottom:34px}.intro h1{font-size:30px;font-weight:550;letter-spacing:1px;margin:0 0 13px}.intro p{font-size:12px;color:#8894ac;margin:0;line-height:1.8;max-width:800px;word-break:break-all}.stats{display:flex;gap:35px;flex-shrink:0}.stat{border-left:1px solid #3b4353;padding-left:20px;min-width:85px}.stat b{font-weight:450;font-size:27px;display:block;line-height:1.3}.stat small{display:block;font-size:10px;color:#8b99b3;margin-top:8px}.stat b em{font-size:15px;font-style:normal;color:#6d7a93}.toolbar{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid #313a4c;padding-bottom:19px;margin-bottom:30px}.filters{display:flex;gap:6px;overflow:auto}.filter{border:1px solid transparent;background:none;color:#94a1b9;white-space:nowrap;padding:9px 13px;border-radius:6px;font-size:11px}.filter.active{background:#293952;border-color:#41567b;color:#c7d9ff}.search{background:#222936;border:1px solid #3b465b;border-radius:6px;padding:9px 12px;color:#d8e3f8;width:210px;min-width:100px;font-size:11px}.search::placeholder{color:#7c8aa4}.character{margin-bottom:33px}.character-heading{margin-bottom:17px}.character-heading>div{display:flex;align-items:center;gap:13px}.reference{width:35px;height:43px;object-fit:cover;object-position:top;border-radius:5px;background:#3b4352}.character-id{font-size:11px;color:#7c92ba;background:#273248;border:1px solid #394865;padding:5px 7px;border-radius:5px}h2{font-size:18px;font-weight:500;margin:0}.completion{color:#7d8ba5;font-size:10px;margin-left:auto}.character-heading p{font-size:11px;color:#8d9bb4;line-height:1.9;margin:10px 0 0;max-width:1000px}.asset-grid{display:grid;grid-template-columns:.8fr .8fr 1fr 1.5fr 1.5fr;gap:13px}.asset{min-width:0;background:#222936;border:1px solid #343e51;border-radius:10px;overflow:hidden}.asset-label{padding:12px 13px;font-size:11px;color:#b2c0d8;display:flex;justify-content:space-between;align-items:center;gap:6px}.asset-label span{font-size:8px;color:#7d8fae;white-space:nowrap}.image-button{height:270px;width:100%;border:0;padding:0;background:#eeeff1;display:flex;align-items:center;justify-content:center;cursor:zoom-in}.image-button img{display:block;width:100%;height:100%;object-fit:contain}.missing{height:270px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#5f6e89;background:radial-gradient(#354157 .8px,transparent .8px);background-size:17px 17px}.missing>span{font-size:30px;font-weight:200}.missing p{font-size:10px;margin:10px 0 0}.single-kind .asset-grid{grid-template-columns:repeat(auto-fit,minmax(260px,500px))}.single-kind .image-button{height:390px}.empty{text-align:center;color:#8796b2;padding:70px 10px;font-size:13px}footer{border-top:1px solid #313a4c;padding:20px 38px;color:#76839b;display:flex;justify-content:space-between;gap:20px;font-size:10px;line-height:1.8}footer p{margin:0;max-width:900px}.state{white-space:nowrap;flex-shrink:0}.state:before{content:"";display:inline-block;width:5px;height:5px;border-radius:50%;background:#7397d3;margin-right:8px}dialog{border:1px solid #45516a;border-radius:12px;background:#202735;color:#dfe8fa;padding:16px;width:1100px;max-width:96vw;text-align:center}dialog::backdrop{background:#060b13dd}dialog img{max-height:78vh;max-width:100%;object-fit:contain;display:block;margin:auto}.lightbox-bar{display:flex;align-items:center;gap:15px;justify-content:space-between;margin-bottom:13px;font-size:13px}.lightbox-bar button{border:0;background:none;color:#b1c1dd;font-size:24px}dialog a{color:#9bbdff;display:inline-block;margin-top:15px;text-decoration:none;font-size:12px}@media(min-width:1800px){.image-button,.missing{height:340px}}@media(max-width:1100px){.asset-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.asset-grid .asset:nth-child(n+4){grid-column:auto}.intro{align-items:flex-start}.stats{gap:15px}.stat{padding-left:12px;min-width:65px}.intro h1{font-size:24px}.toolbar{flex-wrap:wrap}.search{width:100%}}@media(max-width:680px){header{padding:18px}.workspace{font-size:10px}.header-actions button{font-size:10px;padding:6px 9px}.header-actions button:first-child{display:none}main{padding:25px 16px}.intro{flex-direction:column;gap:23px}.intro h1{font-size:25px}.stats{width:100%;justify-content:space-between}.stat{flex:1}.stat b{font-size:23px}.toolbar{gap:13px}.filters{width:100%}.filter{padding:9px;font-size:10px}.asset-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.asset-grid .asset:last-child{grid-column:1/-1}.image-button,.missing{height:230px}.asset-label{padding:10px;font-size:10px}.character-heading p{font-size:10px}footer{padding:19px 16px;flex-direction:column;font-size:9px}.single-kind .asset-grid{grid-template-columns:1fr}.single-kind .image-button{height:350px}.single-kind .asset{grid-column:1/-1}}
</style></head><body>
<header><span class="logo">幕间</span><span class="header-divider"></span><span class="workspace">人物资产展示大屏</span><div class="header-actions"><button id="expand">全屏展示</button><button id="refresh">刷新展示</button></div></header>
<main><div class="intro"><div><h1>角色的每一面，都在这里。</h1><p>{{TITLE}} · 视频时长 {{DURATION}} · 当前完成度 {{PROGRESS}}%</p></div><div class="stats"><div class="stat"><b>{{CHARACTERS}}</b><small>可识别角色</small></div><div class="stat"><b>{{COMPLETED}} <em>/ {{TOTAL}}</em></b><small>人物资产</small></div><div class="stat"><b>9</b><small>常见情绪</small></div></div></div>
<div class="toolbar"><div class="filters">{{FILTERS}}</div><input class="search" type="search" placeholder="搜索角色或服装特征" aria-label="搜索角色或服装特征"></div>
<div id="characters">{{CARDS}}</div><p id="empty" class="empty" hidden>没有匹配的角色</p></main>
<footer><p>AI 生成素材中的背面、遮挡部位与未展示服饰属于推测补全；人物身份、情绪与设计一致性请人工复核。原片参考保留在资产包中。</p><span class="state">{{STATE}}</span></footer>
<dialog id="lightbox"><div class="lightbox-bar"><span id="lightbox-title"></span><button id="close" aria-label="关闭预览">×</button></div><img id="large-image" alt="人物资产放大预览"><a id="save-image" download>下载原图</a></dialog>
<script>
let selectedKind='all';const search=document.querySelector('.search');
function filter(){let count=0;document.body.classList.toggle('single-kind',selectedKind!=='all');document.querySelectorAll('.character').forEach(el=>{const match=el.dataset.search.toLowerCase().includes(search.value.trim().toLowerCase());el.hidden=!match;if(match)count++;el.querySelectorAll('.asset').forEach(tile=>tile.hidden=selectedKind!=='all'&&tile.dataset.kind!==selectedKind)});document.getElementById('empty').hidden=count>0}
document.querySelectorAll('.filter').forEach(button=>button.addEventListener('click',()=>{selectedKind=button.dataset.filter;document.querySelectorAll('.filter').forEach(b=>b.classList.toggle('active',b===button));filter()}));search.addEventListener('input',filter);
const dialog=document.getElementById('lightbox');document.querySelectorAll('.image-button').forEach(button=>button.addEventListener('click',()=>{const source=button.querySelector('img').src;document.getElementById('large-image').src=source;document.getElementById('lightbox-title').textContent=button.dataset.title;const a=document.getElementById('save-image');a.href=source;a.download=button.dataset.title+'.png';dialog.showModal()}));document.getElementById('close').onclick=()=>dialog.close();dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close()}});document.getElementById('expand').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen()}catch{document.getElementById('expand').textContent='请使用浏览器全屏'}};document.getElementById('refresh').onclick=()=>location.reload();filter();
</script></body></html>'''
