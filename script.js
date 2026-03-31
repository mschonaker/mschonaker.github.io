let postsContainer;
let posts = [];
let currentView = null;

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
    return `<pre><code class="language-${lang}">${escaped}</code></pre>`;
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
  // Sort posts by date descending (newest first)
  const sorted = [...posts].sort((a, b) => b.timestamp - a.timestamp);
  
  const hashId = getHashParams();
  if (hashId) {
    const post = posts.find(p => p.id === hashId);
    if (post && post.type === 'article') {
      currentView = hashId;
      await renderArticle(post);
      return;
    }
  } else if (currentView) {
    const post = posts.find(p => p.id === currentView);
    if (post && post.type === 'article') {
      await renderArticle(post);
      return;
    }
  }
  
  const articleLinks = await Promise.all(sorted.map(async post => {
    if (post.type === 'article') {
      try {
        const res = await fetch(post.file);
        const md = await res.text();
        const match = md.match(/^# (.+)$/m);
        const title = match ? match[1] : 'Untitled';
        return `
          <div class="post" id="post-${post.id}">
            <div class="post-content">
              <a href="#article/${post.id}" class="article-link">
                ${escapeHtml(title)}
              </a>
              <span class="article-date"> ${formatDate(post.timestamp)}</span>
              ${post.summary ? `<div class="article-summary">${escapeHtml(post.summary)}</div>` : ''}
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
    return `
      <div class="post" id="post-${post.id}">
        <div class="post-content">${escapeHtml(post.content)}</div>
        <div class="post-meta">
          ${formatDate(post.timestamp)}
        </div>
      </div>
    `;
  }));
  
  postsContainer.innerHTML = articleLinks.join('');
}

async function renderArticle(post) {
  try {
    const response = await fetch(post.file);
    let markdown = await response.text();
    markdown = markdown.replace(/^---[\s\S]*?---[\n\r]*/, '');
    const titleMatch = markdown.match(/^# (.+)$/m);
    const title = titleMatch ? titleMatch[1] : 'Untitled';
    markdown = markdown.replace(/^# .+$/m, '');
    const html = parseMarkdown(markdown);
    
    postsContainer.innerHTML = `
      <div class="article-view">
        <div class="article-header">
          <a href="#" onclick="closeArticle(); return false;" class="back-link">← back</a>
        </div>
        <div class="article-content">
          <h1>${escapeHtml(title)}</h1>
          <div class="article-date">${formatDate(post.timestamp)}</div>
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
