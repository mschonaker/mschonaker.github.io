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
    renderPosts();
  } catch (error) {
    posts = [];
    renderPosts();
  }
}

function generateId() {
  return Math.random().toString(36).substring(2, 10);
}

function formatDate(timestamp) {
  const date = new Date(timestamp * 1000);
  return date.toISOString().replace('T', ' ').substring(0, 19);
}

function escapeHtmlEntities(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function highlightXmlCode(code) {
  return code
    .replace(/(&lt;\/?[\w-]+)/g, '<span class="xml-tag">$1</span>')
    .replace(/(\s[\w-]+)=/g, ' <span class="xml-attr">$1</span>=')
    .replace(/"([^"]*)"/g, '"<span class="xml-value">$1</span>"');
}

function parseMarkdown(text) {
  let html = text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/```(\w+)?\n([\s\S]*?)```/gim, (match, lang, code) => {
      const highlighted = lang === 'xml' ? highlightXmlCode(code) : code;
      return '<pre><code class="lang-' + (lang || '') + '">' + escapeHtmlEntities(highlighted) + '</code></pre>';
    })
    .replace(/`([^`]+)`/gim, (match, code) => {
      return '<code>' + escapeHtmlEntities(code) + '</code>';
    })
    .replace(/^- (.*$)/gim, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/(\d+)\. (.*$)/gim, '<li>$2</li>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/---/g, '<hr>');
  
  html = html.replace(/^(<h[1-3]>.*<\/h[1-3]>\n?)+/gim, (match) => match);
  html = html.replace(/(<ul>.*<\/ul>\n?)+/g, (match) => match.replace(/\n?/g, ''));
  
  return '<p>' + html + '</p>';
}

async function renderPosts() {
  const sorted = [...posts].sort((a, b) => b.timestamp - a.timestamp);
  
  if (currentView) {
    const post = posts.find(p => p.id === currentView);
    if (post && post.type === 'article') {
      await renderArticle(post);
      return;
    }
  }
  
  postsContainer.innerHTML = sorted.map(post => {
    if (post.type === 'article') {
      return `
        <div class="post" id="post-${post.id}">
          <div class="post-content">
            <a href="#" onclick="viewArticle('${post.id}'); return false;" class="article-link">
              ${escapeHtml(post.title)}
            </a>
          </div>
          <div class="post-meta">
            <span class="prompt">></span> ${formatDate(post.timestamp)}
          </div>
        </div>
      `;
    }
    return `
      <div class="post" id="post-${post.id}">
        <div class="post-content">${escapeHtml(post.content)}</div>
        <div class="post-meta">
          <span class="prompt">></span> ${formatDate(post.timestamp)}
        </div>
        <div class="post-actions">
          <a href="#" onclick="openEditModal('${post.id}'); return false;">edit</a>
          <a href="#" onclick="deletePost('${post.id}'); return false;">delete</a>
        </div>
      </div>
    `;
  }).join('');
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
        <div class="article-content">${html}</div>
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
  renderPosts();
}

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

newPostInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    addPost(newPostInput.value);
  }
});

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
