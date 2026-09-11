'use strict';

const list=document.querySelector('#publication-list');

function textElement(tag,className,text){
  const element=document.createElement(tag);
  if(className)element.className=className;
  element.textContent=text;
  return element;
}

function publicationCard(item,index){
  const article=document.createElement('article');
  article.className='publication-item';

  const figure=document.createElement('div');
  figure.className='publication-figure';
  const imagePath=String(item.image||'');
  if(/^publication-assets\/[0-9a-f]{32}\.(png|jpg|webp)$/.test(imagePath)){
    const image=document.createElement('img');
    image.src=`./${imagePath}?v=${encodeURIComponent(item.updated_at||'')}`;
    image.alt=item.image_alt||`${item.title||'研究成果'}的代表图`;
    image.loading='lazy';
    figure.append(image);
  }else{
    figure.append(textElement('span','', '代表图待补充'));
  }

  const info=document.createElement('div');
  info.className='publication-info';
  info.append(textElement('p','publication-type',`PUBLICATION ${String(index+1).padStart(2,'0')}`));
  info.append(textElement('h3','',item.title||'未命名成果'));
  info.append(textElement('p','publication-authors',item.authors||'作者信息待补充'));
  info.append(textElement('p','publication-venue',[item.venue,item.year].filter(Boolean).join('，')||'发表信息待补充'));
  if(item.summary)info.append(textElement('p','publication-summary',item.summary));
  let publicationUrl=null;
  try{publicationUrl=new URL(item.url);if(!['http:','https:'].includes(publicationUrl.protocol))publicationUrl=null}catch{}
  if(publicationUrl){
    const link=textElement('a','publication-link','查看论文 ↗');
    link.href=publicationUrl.href;
    link.target='_blank';
    link.rel='noopener noreferrer';
    info.append(link);
  }

  article.append(figure,info);
  return article;
}

async function loadPublications(){
  try{
    const response=await fetch(`./publications.json?v=${Date.now()}`,{cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const items=await response.json();
    if(!Array.isArray(items))throw new Error('成果数据格式错误');
    list.replaceChildren();
    if(!items.length){
      list.append(textElement('p','publication-empty','小组成果正在整理中。'));
      return;
    }
    items.forEach((item,index)=>list.append(publicationCard(item,index)));
  }catch(error){
    list.replaceChildren(textElement('p','publication-empty','成果暂时无法加载，请稍后刷新。'));
  }
}

loadPublications();
