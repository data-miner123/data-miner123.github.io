'use strict';
const $=s=>document.querySelector(s);
const $$=s=>document.querySelectorAll(s);
const state={site:null,user:null,reports:[],literature:[],users:[],adminMembers:[],filter:'all',query:'',literatureQuery:'',detailRequest:0,literatureRequest:0,currentLiterature:null};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const kindName=k=>k==='weekly'?'周报':'日报';
const statusName=s=>({pending:'待审核',active:'正常',disabled:'已停用'}[s]||s);
const formatDateTime=value=>{const d=new Date(value);return Number.isNaN(d.getTime())?String(value||''):d.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})};

async function api(url,options={}){
  const response=await fetch(url,options); let result;
  try{result=await response.json()}catch{throw new Error('服务器返回了无法读取的内容。')}
  if(!response.ok)throw new Error(result.error||'请求失败，请稍后重试。'); return result;
}
function jsonOptions(method,body={}){return{method,headers:{'Content-Type':'application/json','X-Requested-With':'VISGroup'},body:JSON.stringify(body)}}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,4200)}

function reportRow(r,admin=false){
  return `<div class="${admin?'admin-row':'report-row-wrap'}"><button class="report-row" data-report="${esc(r.id)}"><div class="report-row-top"><span class="badge ${r.kind==='weekly'?'weekly':''}">${kindName(r.kind)}</span><time class="report-date">${esc(r.date)}</time>${r.example?'<span class="example-label">示例</span>':''}</div><h3>${esc(r.title)}<span aria-hidden="true">↗</span></h3><p class="report-summary">${esc(r.summary)}</p><p class="report-author">${esc(r.author)}${r.filename?' · 含附件':''}</p></button>${admin?`<button class="button danger" data-delete-report="${esc(r.id)}" data-title="${esc(r.title)}">删除</button>`:''}</div>`;
}
function literatureRow(item,admin=false){
  const publication=[item.year,item.source].filter(Boolean).join(' · ')||'来源待补充';
  return `<div class="${admin?'admin-row':'literature-row-wrap'}"><button class="literature-row" data-literature="${esc(item.id)}"><div class="literature-row-top"><span class="literature-type">${item.filename?'文献附件':'外部链接'}</span><span class="literature-publication">${esc(publication)}</span><span class="comment-chip">${Number(item.comment_count)||0} 条评论</span></div><h3>${esc(item.title)}<span aria-hidden="true">↗</span></h3><p class="literature-authors">${esc(item.authors)}</p>${item.notes?`<p class="literature-summary">${esc(item.notes)}</p>`:''}<p class="literature-uploader">由 ${esc(item.uploader)} 上传${item.filename?` · ${esc(item.filename)}`:''}</p></button>${admin?`<button class="button danger" data-delete-literature="${esc(item.id)}" data-title="${esc(item.title)}">删除</button>`:''}</div>`;
}
function renderReports(){
  if(!state.user){
    const prompt='<div class="empty-state"><h3>登录后查看小组研究日志</h3><p>已有账号可直接登录；新成员提交注册申请后，由管理员审核。</p><button class="button primary" data-auth>登录 / 注册</button></div>';
    $('#recent-reports').innerHTML=prompt; $('#all-reports').innerHTML=prompt; $('#report-count').textContent=''; return;
  }
  $('#recent-reports').innerHTML=state.reports.slice(0,4).map(r=>reportRow(r)).join('')||'<p class="empty-state">还没有研究记录。</p>';
  const q=state.query.toLocaleLowerCase();
  const rows=state.reports.filter(r=>(state.filter==='all'||r.kind===state.filter)&&`${r.title} ${r.author} ${r.summary}`.toLocaleLowerCase().includes(q));
  $('#report-count').textContent=`共 ${rows.length} 份${state.filter==='all'?'报告':kindName(state.filter)}`;
  $('#all-reports').innerHTML=rows.map(r=>reportRow(r)).join('')||'<p class="empty-state">暂无符合条件的报告。</p>';
}
function renderLiterature(){
  if(!state.user){
    $('#literature-count').textContent='';
    $('#literature-list').innerHTML='<div class="empty-state"><h3>登录后进入小组文献库</h3><p>审核通过的成员可以上传文献、下载附件并参与评论。</p><button class="button primary" data-auth>登录 / 注册</button></div>';
    return;
  }
  const q=state.literatureQuery.toLocaleLowerCase();
  const rows=state.literature.filter(item=>`${item.title} ${item.authors} ${item.source} ${item.year} ${item.notes}`.toLocaleLowerCase().includes(q));
  $('#literature-count').textContent=`共 ${rows.length} 篇文献`;
  $('#literature-list').innerHTML=rows.map(item=>literatureRow(item)).join('')||'<p class="empty-state">暂无符合条件的文献，上传第一篇开始讨论吧。</p>';
}
function renderAccount(){
  const logged=Boolean(state.user); $('#login-button').hidden=logged; $('#logout-button').hidden=!logged; $('#profile-button').hidden=!logged; $('#account-name').hidden=!logged;
  $$('[data-compose],[data-literature-compose]').forEach(button=>button.hidden=!logged); $('#admin-nav').hidden=state.user?.role!=='admin';
  $('#account-name').textContent=logged?`${state.user.display_name}${state.user.role==='admin'?' · 管理员':''}`:'';
}
function renderSite(){
  const s=state.site; $('#brand-name').textContent=s.name;$('#footer-name').textContent=s.name;$('#group-name').innerHTML=`${esc(s.name)}<span class="accent">.</span>`;
  for(const [id,key] of [['group-name-zh','name_zh'],['subtitle','subtitle'],['description','description'],['about','about'],['demo-note','notice']])$(`#${id}`).textContent=s[key]||'';
  $('#demo-note').hidden=!s.notice; $('#view-people .demo-note').textContent=s.notice||''; $('#view-people .demo-note').hidden=!s.notice;
  $('#news-list').innerHTML=(s.news||[]).map((news,index)=>`<button type="button" class="news-item" data-news="${index}" aria-label="查看动态：${esc(news.title)}"><time>${esc(news.date)}</time><span class="news-tag">${esc(news.tag)}</span><h3>${esc(news.title)}<span aria-hidden="true">↗</span></h3><p>${esc(news.text)}</p></button>`).join('')||'<p class="empty-state">暂无小组动态。</p>';
  $('#member-list').innerHTML=(s.members||[]).map(member=>`<article class="member-card"><div class="member-initial">${esc(member.initial||member.name.slice(0,1))}</div><h2>${esc(member.name)}</h2><p>${esc(member.role)}</p><p class="member-area">${esc(member.area)}</p></article>`).join('')||'<p class="empty-state">成员信息待补充。</p>';
}
function renderAdmin(){
  if(state.user?.role!=='admin')return;
  $('#pending-count').textContent=`${state.users.filter(u=>u.status==='pending').length} 个待审核账号`;$('#admin-report-count').textContent=`${state.reports.length} 份研究报告`;$('#admin-literature-count').textContent=`${state.literature.length} 篇文献`;
  $('#admin-news').innerHTML=(state.site.news||[]).map((item,index)=>`<article class="admin-row"><div class="admin-news-copy"><h3>${esc(item.title)}</h3><p>${esc(item.date)} · ${esc(item.tag)} · ${esc(item.text)}</p></div><div class="row-actions"><button class="button" data-edit-news="${index}">编辑</button><button class="button danger" data-delete-news="${index}" data-title="${esc(item.title)}">删除</button></div></article>`).join('')||'<p class="empty-state">暂无小组动态。</p>';
  $('#admin-members').innerHTML=state.adminMembers.map((member,index)=>{const options=state.users.map(user=>`<option value="${esc(user.id)}" ${member.user_id===user.id?'selected':''}>${esc(user.display_name)}（@${esc(user.username)} · ${statusName(user.status)}）</option>`).join('');return `<article class="admin-row"><div><h3>${esc(member.name)}</h3><p>${esc(member.role)}${member.area?` · ${esc(member.area)}`:''}</p></div><div class="member-binding"><select aria-label="绑定 ${esc(member.name)} 的账号" data-member-account="${index}"><option value="">未绑定</option>${options}</select><button class="button" data-bind-member="${index}">保存绑定</button></div></article>`}).join('')||'<p class="empty-state">暂无成员资料。</p>';
  $('#admin-users').innerHTML=state.users.map(u=>`<article class="admin-row"><div><h3>${esc(u.display_name)} <span class="status ${u.status}">${statusName(u.status)}</span></h3><p>@${esc(u.username)} · ${u.role==='admin'?'管理员':'成员'} · 注册于 ${esc(u.created_at.slice(0,10))}</p></div><div class="row-actions">${u.status!=='active'?`<button class="button primary" data-user-action="approve" data-user="${u.id}">${u.status==='pending'?'通过':'重新启用'}</button>`:''}${u.status==='pending'?`<button class="button danger" data-user-action="disable" data-user="${u.id}">拒绝</button>`:''}${u.status==='active'&&u.id!==state.user.id?`<button class="button" data-user-action="promote" data-role="${u.role==='admin'?'member':'admin'}" data-user="${u.id}">${u.role==='admin'?'改为成员':'设为管理员'}</button><button class="button danger" data-user-action="disable" data-user="${u.id}">停用</button>`:''}</div></article>`).join('')||'<p class="empty-state">暂无账号。</p>';
  $('#admin-reports').innerHTML=state.reports.map(r=>reportRow(r,true)).join('')||'<p class="empty-state">暂无报告。</p>';
  $('#admin-literature').innerHTML=state.literature.map(item=>literatureRow(item,true)).join('')||'<p class="empty-state">暂无文献。</p>';
}
async function loadAdmin(){if(state.user?.role!=='admin')return;try{[state.users,state.adminMembers]=await Promise.all([api('/api/admin/users'),api('/api/admin/members')]);renderAdmin()}catch(e){toast(e.message)}}
function route(){
  let page=['home','reports','literature','people','admin'].includes(location.hash.slice(1))?location.hash.slice(1):'home';
  if(page==='admin'&&state.user?.role!=='admin')page='home';
  $$('.view').forEach(view=>view.hidden=view.id!==`view-${page}`||!state.site);$$('[data-nav]').forEach(link=>link.dataset.nav===page?link.setAttribute('aria-current','page'):link.removeAttribute('aria-current'));
  document.title=`${state.site?.name||'VIS Group'} · ${{home:'小组主页',reports:'研究日志',literature:'文献资料',people:'小组成员',admin:'管理后台'}[page]}`;
  if(page==='admin')loadAdmin();
}
async function refreshReports(){state.reports=state.user?await api('/api/reports'):[];renderReports();if(state.user?.role==='admin')renderAdmin()}
async function refreshLiterature(){state.literature=state.user?await api('/api/literature'):[];renderLiterature();if(state.user?.role==='admin')renderAdmin()}
async function refreshContent(){await Promise.all([refreshReports(),refreshLiterature()])}
async function load(){
  $('#page-status').hidden=false;$('#page-status').textContent='正在读取小组信息…';
  try{const [site,session]=await Promise.all([api('/api/site'),api('/api/auth/me')]);state.site=site;state.user=session.user;renderSite();renderAccount();await refreshContent();route();$('#page-status').hidden=true}
  catch(e){$('#page-status').innerHTML=`${esc(e.message)} <button id="retry-load">重试</button>`;$('#retry-load').addEventListener('click',load)}
}

function showAuth(register=false){
  $('#login-form').hidden=register;$('#register-form').hidden=!register;$('#login-tab').setAttribute('aria-selected',String(!register));$('#register-tab').setAttribute('aria-selected',String(register));$('#auth-title').textContent=register?'申请加入小组':'成员登录';if(!$('#auth-dialog').open)$('#auth-dialog').showModal();
}
function compose(){if(!state.user)return showAuth();$('#compose-author').textContent=state.user.display_name;const form=$('#report-form');if(!form.elements.date.value){const d=new Date();form.elements.date.value=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}$('#form-error').textContent='';$('#compose-dialog').showModal()}
function composeLiterature(){if(!state.user)return showAuth();$('#literature-uploader').textContent=state.user.display_name;$('#literature-form-error').textContent='';$('#literature-compose-dialog').showModal()}
function composeNews(index=null){
  if(state.user?.role!=='admin')return;const form=$('#news-form');form.reset();form.elements.index.value=index===null?'':String(index);$('#news-form-error').textContent='';
  if(index===null){const d=new Date();form.elements.date.value=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;$('#news-compose-title').textContent='发布小组动态'}
  else{const item=state.site.news[index];if(!item)return;for(const key of ['date','tag','title','text','detail'])form.elements[key].value=item[key]||'';$('#news-compose-title').textContent='编辑小组动态'}
  $('#news-compose-dialog').showModal();
}
async function showProfile(){
  if(!state.user)return showAuth();const form=$('#profile-form');$('#profile-form-error').textContent='';
  try{const profile=await api('/api/profile');for(const key of ['name','initial','role','area'])form.elements[key].value=profile[key]||'';$('#profile-dialog').showModal()}
  catch(error){toast(error.message)}
}
function showNews(index){
  const news=state.site?.news?.[index];if(!news)return;$('#news-detail-tag').textContent=news.tag||'小组动态';$('#news-detail-title').textContent=news.title;$('#news-detail-date').textContent=news.date||'';$('#news-detail-body').textContent=news.detail||news.text||'';$('#news-dialog').showModal();
}
async function showReport(id){
  if(!state.user)return showAuth();const req=++state.detailRequest;$('#detail-title').textContent='正在读取报告…';$('#detail-meta').textContent='';$('#detail-summary').textContent='';$('#detail-body').textContent='';$('#detail-kind').textContent='';$('#detail-attachment').hidden=true;$('#detail-dialog').showModal();
  try{const report=await api(`/api/reports/${encodeURIComponent(id)}`);if(req!==state.detailRequest)return;$('#detail-title').textContent=report.title;$('#detail-kind').textContent=kindName(report.kind);$('#detail-kind').className=`badge ${report.kind==='weekly'?'weekly':''}`;$('#detail-meta').textContent=`${report.author} · ${report.date}${report.example?' · 示例报告':''}`;$('#detail-summary').textContent=report.summary;$('#detail-body').textContent=report.body||'正文见附件。';if(report.filename){$('#detail-attachment').href=`/api/reports/${encodeURIComponent(report.id)}/attachment`;$('#detail-attachment').textContent=`下载附件：${report.filename} ↓`;$('#detail-attachment').hidden=false}}
  catch(e){if(req===state.detailRequest){$('#detail-title').textContent='读取失败';$('#detail-body').textContent=e.message}}
}
function renderComments(comments){
  $('#comment-count').textContent=`${comments.length} 条评论`;
  $('#comment-list').innerHTML=comments.map(comment=>`<article class="comment"><div class="comment-meta"><strong>${esc(comment.author)}</strong><time>${esc(formatDateTime(comment.created_at))}</time></div><p>${esc(comment.body)}</p></article>`).join('')||'<p class="comment-empty">还没有评论，写下第一条想法吧。</p>';
}
async function showLiterature(id){
  if(!state.user)return showAuth();const req=++state.literatureRequest;state.currentLiterature=id;$('#literature-detail-title').textContent='正在读取文献…';$('#literature-detail-authors').textContent='';$('#literature-detail-meta').textContent='';$('#literature-detail-notes').textContent='';$('#literature-file').hidden=true;$('#literature-link').hidden=true;renderComments([]);$('#comment-form .error-text').textContent='';if(!$('#literature-detail-dialog').open)$('#literature-detail-dialog').showModal();
  try{const item=await api(`/api/literature/${encodeURIComponent(id)}`);if(req!==state.literatureRequest)return;$('#literature-detail-title').textContent=item.title;$('#literature-detail-authors').textContent=item.authors;$('#literature-detail-meta').textContent=[item.year,item.source,`由 ${item.uploader} 上传`,formatDateTime(item.created_at)].filter(Boolean).join(' · ');$('#literature-detail-notes').textContent=item.notes||'暂无阅读提示或摘要。';if(item.filename){$('#literature-file').href=`/api/literature/${encodeURIComponent(item.id)}/attachment`;$('#literature-file').textContent=`查看 / 下载：${item.filename} ↗`;$('#literature-file').hidden=false}if(item.url){$('#literature-link').href=item.url;$('#literature-link').hidden=false}renderComments(item.comments||[])}
  catch(e){if(req===state.literatureRequest){$('#literature-detail-title').textContent='读取失败';$('#literature-detail-notes').textContent=e.message}}
}
function fileBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('附件读取失败，请重新选择文件。'));reader.readAsDataURL(file)})}
async function submitSimple(form,url,success){
  const error=form.querySelector('.error-text'),button=form.querySelector('[type=submit]');error.textContent='';button.disabled=true;
  try{const data=Object.fromEntries(new FormData(form));const result=await api(url,jsonOptions('POST',data));form.reset();$('#auth-dialog').close();toast(success||result.message)}catch(e){error.textContent=e.message}finally{button.disabled=false}
}
$('#login-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,error=form.querySelector('.error-text'),button=form.querySelector('[type=submit]');error.textContent='';button.disabled=true;try{const result=await api('/api/auth/login',jsonOptions('POST',Object.fromEntries(new FormData(form))));state.user=result.user;form.reset();$('#auth-dialog').close();renderAccount();await refreshContent();route();toast(`欢迎回来，${state.user.display_name}`)}catch(err){error.textContent=err.message}finally{button.disabled=false}});
$('#register-form').addEventListener('submit',event=>{event.preventDefault();submitSimple(event.currentTarget,'/api/auth/register','注册申请已提交，审核通过后即可登录。')});
$('#report-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=$('#submit-report');$('#form-error').textContent='';button.disabled=true;button.textContent='正在保存…';let saved=false;
  try{const data=Object.fromEntries(['title','kind','date','summary','body'].map(key=>[key,form.elements[key].value.trim()]));const file=$('#attachment').files[0];if(!data.title)throw new Error('请填写标题。');if(!data.body&&!file)throw new Error('请填写正文，或上传一份附件。');if(file){if(!file.size||file.size>5*1024*1024)throw new Error('附件不能为空，且不能超过 5 MB。');data.attachment={name:file.name,data:await fileBase64(file)}}await api('/api/reports',jsonOptions('POST',data));saved=true;form.reset();$('#compose-dialog').close();await refreshReports();location.hash='reports';toast('报告已保存。')}
  catch(err){if(saved)toast('报告已保存，但列表刷新失败，请刷新页面，勿重复提交。');else $('#form-error').textContent=err.message}finally{button.disabled=false;button.textContent='提交报告 ↗'}
});
$('#literature-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=$('#submit-literature'),error=$('#literature-form-error');error.textContent='';button.disabled=true;button.textContent='正在上传…';let saved=false;
  try{const data=Object.fromEntries(['title','authors','source','year','url','notes'].map(key=>[key,form.elements[key].value.trim()]));const file=$('#literature-attachment').files[0];if(!data.title||!data.authors)throw new Error('请填写文献标题和作者。');if(!file&&!data.url)throw new Error('请上传文献附件，或填写文献链接。');if(file){if(!file.size||file.size>20*1024*1024)throw new Error('附件不能为空，且不能超过 20 MB。');data.attachment={name:file.name,data:await fileBase64(file)}}await api('/api/literature',jsonOptions('POST',data));saved=true;form.reset();$('#literature-compose-dialog').close();await refreshLiterature();location.hash='literature';toast('文献已加入资料库。')}
  catch(err){if(saved)toast('文献已保存，但列表刷新失败，请刷新页面，勿重复提交。');else error.textContent=err.message}finally{button.disabled=false;button.textContent='保存文献 ↗'}
});
$('#news-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=$('#submit-news'),error=$('#news-form-error'),index=form.elements.index.value;error.textContent='';button.disabled=true;button.textContent='正在保存…';
  try{const data=Object.fromEntries(['date','tag','title','text','detail'].map(key=>[key,form.elements[key].value.trim()]));const result=await api(index===''?'/api/admin/news':`/api/admin/news/${index}`,jsonOptions('POST',data));state.site.news=result.news;renderSite();renderAdmin();form.reset();$('#news-compose-dialog').close();toast(index===''?'动态已发布。':'动态已更新。')}
  catch(err){error.textContent=err.message}finally{button.disabled=false;button.textContent='保存动态 ↗'}
});
$('#profile-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=$('#submit-profile'),error=$('#profile-form-error');error.textContent='';button.disabled=true;button.textContent='正在保存…';
  try{const data=Object.fromEntries(['name','initial','role','area'].map(key=>[key,form.elements[key].value.trim()]));const result=await api('/api/profile',jsonOptions('POST',data));state.site=result.site;renderSite();if(state.user?.role==='admin')await loadAdmin();$('#profile-dialog').close();toast('个人信息已更新。')}
  catch(err){error.textContent=err.message}finally{button.disabled=false;button.textContent='保存个人信息 ↗'}
});
$('#comment-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=form.querySelector('[type=submit]'),error=form.querySelector('.error-text'),id=state.currentLiterature;error.textContent='';button.disabled=true;
  try{await api(`/api/literature/${encodeURIComponent(id)}/comments`,jsonOptions('POST',{body:form.elements.body.value.trim()}));form.reset();await showLiterature(id);await refreshLiterature();toast('评论已发表。')}catch(err){error.textContent=err.message}finally{button.disabled=false}
});
async function userAction(button){const action=button.dataset.userAction,user=button.dataset.user;if(!confirm(action==='disable'?'确定停用这个账号吗？':'确定执行此操作吗？'))return;try{await api(`/api/admin/users/${user}/${action}`,jsonOptions('POST',{role:button.dataset.role||''}));await loadAdmin();toast('成员账号已更新。')}catch(e){toast(e.message)}}
async function deleteReport(button){if(!confirm(`确定删除“${button.dataset.title}”吗？附件也会一并删除，此操作无法撤销。`))return;try{await api(`/api/reports/${button.dataset.deleteReport}`,jsonOptions('DELETE',{}));await refreshReports();toast('报告已删除。')}catch(e){toast(e.message)}}
async function deleteLiterature(button){if(!confirm(`确定删除文献“${button.dataset.title}”吗？附件和全部评论也会一并删除。`))return;try{await api(`/api/literature/${button.dataset.deleteLiterature}`,jsonOptions('DELETE',{}));await refreshLiterature();toast('文献已删除。')}catch(e){toast(e.message)}}
async function deleteNews(button){if(!confirm(`确定删除动态“${button.dataset.title}”吗？此操作无法撤销。`))return;try{const result=await api(`/api/admin/news/${button.dataset.deleteNews}/delete`,jsonOptions('POST',{}));state.site.news=result.news;renderSite();renderAdmin();toast('动态已删除。')}catch(e){toast(e.message)}}
async function bindMember(button){const index=button.dataset.bindMember,select=$(`[data-member-account="${index}"]`);button.disabled=true;try{const result=await api(`/api/admin/members/${index}/bind`,jsonOptions('POST',{user_id:select.value}));state.adminMembers=result.members;renderAdmin();toast(select.value?'成员账号已绑定。':'成员账号已解除绑定。')}catch(e){toast(e.message);button.disabled=false}}
document.addEventListener('click',event=>{
  const composeButton=event.target.closest('[data-compose]'),literatureCompose=event.target.closest('[data-literature-compose]'),newsCompose=event.target.closest('[data-news-compose]'),editNews=event.target.closest('[data-edit-news]'),deleteNewsButton=event.target.closest('[data-delete-news]'),bindMemberButton=event.target.closest('[data-bind-member]'),close=event.target.closest('[data-close]'),report=event.target.closest('[data-report]'),literature=event.target.closest('[data-literature]'),news=event.target.closest('[data-news]'),filter=event.target.closest('[data-filter]'),auth=event.target.closest('[data-auth]'),userActionButton=event.target.closest('[data-user-action]'),deleteButton=event.target.closest('[data-delete-report]'),deleteLiteratureButton=event.target.closest('[data-delete-literature]');
  if(composeButton)compose();if(literatureCompose)composeLiterature();if(newsCompose)composeNews();if(editNews)composeNews(Number(editNews.dataset.editNews));if(deleteNewsButton)deleteNews(deleteNewsButton);if(bindMemberButton)bindMember(bindMemberButton);if(close)document.getElementById(close.dataset.close).close();if(report)showReport(report.dataset.report);if(literature)showLiterature(literature.dataset.literature);if(news)showNews(Number(news.dataset.news));if(auth)showAuth();if(userActionButton)userAction(userActionButton);if(deleteButton)deleteReport(deleteButton);if(deleteLiteratureButton)deleteLiterature(deleteLiteratureButton);
  if(filter){state.filter=filter.dataset.filter;$$('[data-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button===filter)));renderReports()}
});
$('#login-button').addEventListener('click',()=>showAuth());$('#login-tab').addEventListener('click',()=>showAuth(false));$('#register-tab').addEventListener('click',()=>showAuth(true));
$('#profile-button').addEventListener('click',showProfile);
$('#logout-button').addEventListener('click',async()=>{try{await api('/api/auth/logout',jsonOptions('POST',{}));state.user=null;state.reports=[];state.literature=[];state.users=[];state.adminMembers=[];renderAccount();renderReports();renderLiterature();location.hash='home';route();toast('已退出登录。')}catch(e){toast(e.message)}});
$('#detail-dialog').addEventListener('close',()=>state.detailRequest++);$('#literature-detail-dialog').addEventListener('close',()=>{state.literatureRequest++;state.currentLiterature=null});$('#search').addEventListener('input',event=>{state.query=event.target.value.trim();renderReports()});$('#literature-search').addEventListener('input',event=>{state.literatureQuery=event.target.value.trim();renderLiterature()});window.addEventListener('hashchange',()=>{route();window.scrollTo(0,0)});load();
