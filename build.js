const fs = require('fs');
const path = require('path');

function parseFrontMatter(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return null;

  const frontMatter = {};
  const lines = match[1].split('\n');

  for (const line of lines) {
    const colonIdx = line.indexOf(':');
    if (colonIdx === -1) continue;
    const key = line.slice(0, colonIdx).trim();
    const value = line.slice(colonIdx + 1).trim();
    frontMatter[key] = value;
  }

  return frontMatter;
}

function parseDate(dateStr) {
  const date = new Date(dateStr);
  return Math.floor(date.getTime() / 1000);
}

function extractTitle(content) {
  const match = content.match(/^# (.+)$/m);
  return match ? match[1] : 'Untitled';
}

const postsDir = '_posts';
const outputFile = 'posts.json';

const files = fs.readdirSync(postsDir).filter(f => f.endsWith('.md'));

const posts = files.map(file => {
  const content = fs.readFileSync(path.join(postsDir, file), 'utf8');
  const frontMatter = parseFrontMatter(content);

  if (!frontMatter) {
    console.error(`No front matter found in ${file}`);
    return null;
  }

  const post = {
    id: frontMatter.id,
    type: 'article',
    file: `${postsDir}/${file}`,
    timestamp: parseDate(frontMatter.date),
    summary: frontMatter.summary
  };

  return post;
}).filter(Boolean);

posts.sort((a, b) => b.timestamp - a.timestamp);

fs.writeFileSync(outputFile, JSON.stringify(posts, null, 2));
console.log(`Generated ${outputFile} with ${posts.length} posts`);
