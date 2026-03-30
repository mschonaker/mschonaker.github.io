const postsContainer = document.getElementById('posts');

let posts = [];
let currentView = null;

async function loadPosts() {
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
  return date.toISOString().replace('T', ' ').substring(0, 19);
}

function parseMarkdown(text) {
  return marked.parse(text);
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
            </div>
            <div class="post-meta">
              <span class="prompt">></span> ${formatDate(post.timestamp)}
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
            </div>
            <div class="post-meta">
              <span class="prompt">></span> ${formatDate(post.timestamp)}
            </div>
          </div>
        `;
      }
    }
    return `
      <div class="post" id="post-${post.id}">
        <div class="post-content">${escapeHtml(post.content)}</div>
        <div class="post-meta">
          <span class="prompt">></span> ${formatDate(post.timestamp)}
        </div>
      </div>
    `;
  }));
  
  postsContainer.innerHTML = articleLinks.join('');
}

async function renderArticle(post) {
  try {
    const response = await fetch(post.file);
    const markdown = await response.text();
    const html = parseMarkdown(markdown);
    
    postsContainer.innerHTML = `
      <div class="article-view">
        <div class="article-header">
          <a href="#" onclick="closeArticle(); return false;" class="back-link">← back</a>
        </div>
        <div class="article-content">
          ${html}
        </div>
      </div>
    `;
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

loadPosts();
