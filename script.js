async function loadPosts() {
  postsContainer = document.getElementById('posts');
  if (!postsContainer) return;
  try {
    const response = await fetch('posts.json');
    posts = await response.json();
  } catch (error) {
    posts = [];
  }
  
  const hashId = getHashParams();
  if (hashId) {
    const post = posts.find(p => p.id === hashId);
    if (post && post.type === 'article') {
      currentView = hashId;
      await renderArticle(post);
      return;
    }
  }
  
  renderPosts();
}

function formatDate(timestamp) {
  const date = new Date(timestamp * 1000);
  return '<span class="prompt">></span> ' + date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

function parseMarkdown(text) {
  const renderer = new marked.Renderer();
  renderer.code = function(code, lang) {
    if (lang === 'mermaid') {
      return `<div class="mermaid">${code}</div>`;
    }
    const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `<div class="code-block"><button class="copy-btn" type="button" title="Copy to clipboard">Copy</button><pre><code class="language-${lang}">${escaped}</code></pre></div>`;
  };
  return marked.parse(text, { renderer });
}

function getHashParams() {
  const hash = window.location.hash.slice(1);
  if (hash.startsWith('article/')) {
    return hash.replace('article/', '');
  }
  return null;
}

function setHash(id) {
  window.location.hash = 'article/' + id;
}

function clearHash() {
  history.replaceState(null, '', window.location.pathname);
}

async function renderPosts() {
  const sorted = [...posts].sort((a, b) => b.timestamp - a.timestamp);
  
  const hashId = getHashParams();
  if (hashId) {
    const post = posts.find(p => p.id === hashId);
    if (post && post.type === 'article') {
      await renderArticle(post);
      return;
    }
  }
  
  renderTagBar();
  
  const visible = activeTag
    ? sorted.filter(p => (p.tags || []).includes(activeTag))
    : sorted;
  
  const articleLinks = await Promise.all(visible.map(async post => {
    if (post.type === 'article') {
      try {
        const res = await fetch(post.file);
        const md = await res.text();
        const match = md.match(/^# (.+)$/m);
        const title = match ? match[1] : 'Untitled';
        const heroImage = post.image || (md.match(/^\s*!\[[^\]]*\]\(([^)\s]+)/) || [])[1];
        const heroClass = heroImage ? ' post-hero' : '';
        const heroStyle = heroImage ? ` style="--hero: url('${escapeHtml(heroImage)}')"` : '';
        return `
          <div class="post${heroClass}" id="post-${post.id}"${heroStyle}>
            <div class="post-content">
              <a href="#article/${post.id}" class="article-link">
                ${escapeHtml(title)}
              </a>
              <span class="article-date"> ${formatDate(post.timestamp)}</span>
              ${post.summary ? `<div class="article-summary">${escapeHtml(post.summary)}</div>` : ''}
              ${tagPills(post.tags)}
            </div>
          </div>
        `;
      } catch (e) {
        return `
          <div class="post" id="post-${post.id}">
            <div class="post-content">
              <a href="#article/${post.id}" class="article-link">
                Article
              </a>
              <span class="article-date"> ${formatDate(post.timestamp)}</span>
            </div>
          </div>
        `;
      }
    }
    return '';
  }));
  
  postsContainer.innerHTML = articleLinks.join('');
}

function cssHeroTheme(id) {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return 'hero-theme-' + (hash % 5);
}

function tagColor(tag) {
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = (hash * 31 + tag.charCodeAt(i)) >>> 0;
  }
  return hash % 360;
}

function tagPills(tags) {
  if (!tags || !tags.length) return '';
  return '<div class="tag-list">' + tags.map(tag => {
    const hue = tagColor(tag);
    return `<span class="tag-pill" style="--pill-hue: ${hue}">${escapeHtml(tag)}</span>`;
  }).join('') + '</div>';
}

let activeTag = null;
let currentView = null;

function renderTagBar() {
  const bar = document.getElementById('tag-bar');
  if (!bar) return;
  const counts = new Map();
  posts.forEach(post => (post.tags || []).forEach(tag => {
    counts.set(tag, (counts.get(tag) || 0) + 1);
  }));
  if (!counts.size) {
    bar.hidden = true;
    return;
  }
  const tags = [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || a.localeCompare(b));
  bar.innerHTML = tags.map(tag => {
    const hue = tagColor(tag);
    const active = tag === activeTag ? ' tag-pill-active' : '';
    return `<span class="tag-pill${active}" style="--pill-hue: ${hue}" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`;
  }).join('');
  bar.hidden = false;
}

function selectTag(tag) {
  activeTag = activeTag === tag ? null : tag;
  renderTagBar();
  renderPosts();
}

document.addEventListener('click', (event) => {
  const pill = event.target.closest('#tag-bar .tag-pill');
  if (!pill) return;
  selectTag(pill.dataset.tag);
});

async function renderArticle(post) {
  const bar = document.getElementById('tag-bar');
  if (bar) bar.hidden = true;
  try {
    const response = await fetch(post.file);
    let markdown = await response.text();
    markdown = markdown.replace(/^---[\s\S]*?---[\n\r]*/, '');
    const titleMatch = markdown.match(/^# (.+)$/m);
    const title = titleMatch ? titleMatch[1] : 'Untitled';
    markdown = markdown.replace(/^# .+$/m, '');
    let heroImage = post.image;
    const leadingImage = markdown.match(/^\s*!\[[^\]]*\]\(([^)\s]+)/);
    if (leadingImage) {
      if (!heroImage) heroImage = leadingImage[1];
      markdown = markdown.replace(/^\s*!\[[^\]]*\]\([^)]*\)[^\n]*\n/, '');
    }
    const html = parseMarkdown(markdown).replace(
      /<table>([\s\S]*?)<\/table>/g,
      '<div class="table-wrap"><table>$1</table></div>'
    );
    
    postsContainer.innerHTML = `
      <div class="article-view">
        <div class="article-header">
          <a href="#" onclick="closeArticle(); return false;" class="back-link">← back</a>
        </div>
        <div class="article-content">
          ${heroImage
            ? `<div class="article-hero">
                 <img src="${escapeHtml(heroImage)}" alt="${escapeHtml(title)}">
                 <h1 class="article-hero-title">${escapeHtml(title)}</h1>
               </div>`
            : `<div class="article-hero article-hero-css ${cssHeroTheme(post.id)}">
                 <h1 class="article-hero-title">${escapeHtml(title)}</h1>
               </div>`}
          <div class="article-date">${formatDate(post.timestamp)}</div>
          ${tagPills(post.tags)}
          ${html}
        </div>
      </div>
    `;
    try {
      if (typeof mermaid !== 'undefined' && document.querySelector('.mermaid')) {
        await mermaid.run({ querySelector: '.mermaid' });
      }
      postsContainer.querySelectorAll('pre code').forEach(block => {
        const classes = block.className.split(' ').filter(c => c.startsWith('language-'));
        if (classes.length) {
          const lang = classes[0].replace('language-', '');
          if (Prism.languages[lang]) {
            block.classList.add('language-' + lang);
            block.innerHTML = Prism.highlight(block.textContent, Prism.languages[lang], lang);
          }
        }
      });
    } catch (e) {
      console.error('Highlight error:', e);
    }
  } catch (error) {
    postsContainer.innerHTML = '<div class="post">Error loading article</div>';
  }
}

function viewArticle(id) {
  currentView = id;
  const post = posts.find(p => p.id === id);
  if (post) {
    renderArticle(post);
  }
}

function closeArticle() {
  currentView = null;
  clearHash();
  renderPosts();
}

window.addEventListener('hashchange', () => {
  const hashId = getHashParams();
  if (hashId) {
    viewArticle(hashId);
  } else {
    closeArticle();
  }
});

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function copyViaExecCommand(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand('copy');
  } finally {
    textarea.remove();
  }
}

document.addEventListener('click', (event) => {
  if (event.target.closest('a, button')) return;
  if (window.getSelection().toString()) return;
  const card = event.target.closest('.post');
  if (!card) return;
  const link = card.querySelector('.article-link');
  if (link) {
    window.location.hash = link.getAttribute('href').slice(1);
  }
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('.copy-btn');
  if (!button) return;
  const code = button.closest('.code-block').querySelector('code');
  const text = code.textContent;
  const showCopied = () => {
    button.textContent = 'Copied!';
    setTimeout(() => {
      button.textContent = 'Copy';
    }, 1500);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(showCopied, () => {
      if (copyViaExecCommand(text)) showCopied();
    });
  } else if (copyViaExecCommand(text)) {
    showCopied();
  }
});

document.addEventListener('DOMContentLoaded', () => {
  if (typeof Prism !== 'undefined') {
    Prism.languages.zig = {
      'comment': {
        pattern: /\/\/[^\n]*/g,
        greedy: true
      },
      'string': {
        pattern: /(["'`])(?:(?!\1)[^\\]|\\.)*?\1/g,
        greedy: true
      },
      'keyword': /\b(align|allowzero|and|anyerror|anytype|anyframe|anyop|as|asm|async|await|break|catch|comptime|const|continue|defer|else|enum|errdefer|error|export|extern|false|fn|for|if|inline|noinline|nosuspend|null|opaque|or|orelse|packed|pub|resume|return|struct|suspend|switch|test|threadlocal|true|try|typeof|undefined|union|unaligned|usingnamespace|var|volatile|while)\b/g,
      'builtin': /\b(void|bool|u8|u16|u32|u64|u128|usize|i8|i16|i32|i64|i128|isize|f16|f32|f64|f128|comptime_int|comptime_float|noreturn|type|anyerror|anyframe|anytype)\b/g,
      'number': {
        pattern: /\b\d+\.?\d*\b/g,
        greedy: true
      },
    };
  }
  if (typeof mermaid !== 'undefined') {
    mermaid.initialize({ startOnLoad: false, theme: 'dark' });
  }
  loadPosts();
});
