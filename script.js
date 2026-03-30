const postsContainer = document.getElementById('posts');
const newPostInput = document.getElementById('newPost');
const editModal = document.getElementById('editModal');
const editContent = document.getElementById('editContent');
const editIdSpan = document.getElementById('editId');
const saveEditBtn = document.getElementById('saveEdit');
const cancelEditBtn = document.getElementById('cancelEdit');

let posts = [];
let editingId = null;
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

function generateId() {
  return Math.random().toString(36).substring(2, 10);
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

function savePosts() {
  const blob = new Blob([JSON.stringify(posts, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'posts.json';
  a.click();
  URL.revokeObjectURL(url);
  
  setTimeout(() => {
    const text = JSON.stringify(posts, null, 2);
    navigator.clipboard.writeText(text).then(() => {
      alert('posts.json updated. Copy the content and save it to posts.json');
    }).catch(() => {
      alert('posts.json content:\n\n' + text);
    });
  }, 100);
}

function addPost(content) {
  if (!content.trim()) return;
  
  const post = {
    id: generateId(),
    content: content.trim(),
    timestamp: Math.floor(Date.now() / 1000)
  };
  
  posts.push(post);
  savePostsToFile(post);
  renderPosts();
  newPostInput.value = '';
}

function savePostsToFile(newPost) {
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/save-post', true);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.send(JSON.stringify({ posts: posts }));
}

async function saveAllPosts() {
  const content = JSON.stringify(posts, null, 2);
  const blob = new Blob([content], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'posts.json';
  a.click();
  URL.revokeObjectURL(url);
}

function openEditModal(id) {
  editingId = id;
  const post = posts.find(p => p.id === id);
  if (post) {
    editIdSpan.textContent = id;
    editContent.value = post.content;
    editModal.style.display = 'flex';
    editContent.focus();
  }
}

function closeEditModal() {
  editModal.style.display = 'none';
  editingId = null;
}

function updatePost(id, content) {
  const post = posts.find(p => p.id === id);
  if (post) {
    post.content = content.trim();
    post.timestamp = Math.floor(Date.now() / 1000);
    saveAllPosts();
    renderPosts();
  }
  closeEditModal();
}

function deletePost(id) {
  if (confirm('Delete this post?')) {
    posts = posts.filter(p => p.id !== id);
    saveAllPosts();
    renderPosts();
  }
}

if (newPostInput) {
  newPostInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      addPost(newPostInput.value);
    }
  });
}

saveEditBtn.addEventListener('click', () => {
  if (editingId) {
    updatePost(editingId, editContent.value);
  }
});

cancelEditBtn.addEventListener('click', closeEditModal);

editContent.addEventListener('keypress', (e) => {
  if (e.key === 'Enter' && e.ctrlKey) {
    if (editingId) {
      updatePost(editingId, editContent.value);
    }
  }
});

loadPosts();
