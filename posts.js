(() => {
  'use strict';
  const root = document.getElementById('posts');
  const status = document.getElementById('feed-status');
  const safeURL = value => { if (!String(value || '').trim()) return ''; try { const u = new URL(value, window.location.href); return ['http:', 'https:'].includes(u.protocol) ? u.href : ''; } catch { return ''; } };
  const text = (item, tag) => item.getElementsByTagName(tag)[0]?.textContent?.trim() || '';
  function plainText(value) {
    const template = document.createElement('template'); template.innerHTML = value;
    function read(node) {
      if (node.nodeType === Node.TEXT_NODE) return node.textContent;
      if (['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT'].includes(node.nodeName)) return '';
      if (node.nodeName === 'BR') return '\n';
      const result = [...node.childNodes].map(read).join('');
      return result + (['P', 'DIV', 'LI'].includes(node.nodeName) ? '\n\n' : '');
    }
    return read(template.content).replace(/\n{3,}/g, '\n\n').trim();
  }
  function action(label, url) { const a = document.createElement('a'); a.textContent = label; a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; }
  async function render() {
    try {
      const response = await fetch(new URL('feed.xml', window.location.href), { cache: 'no-store' });
      if (!response.ok) throw new Error('Feed unavailable');
      const xml = new DOMParser().parseFromString(await response.text(), 'application/xml');
      if (xml.querySelector('parsererror')) throw new Error('Invalid feed');
      const seen = new Set();
      const items = [...xml.getElementsByTagName('item')].filter(item => { const key = text(item, 'guid') || text(item, 'link'); if (!key || seen.has(key)) return false; seen.add(key); return true; });
      items.sort((a, b) => (Date.parse(text(b, 'pubDate')) || 0) - (Date.parse(text(a, 'pubDate')) || 0));
      const selected = new URL(window.location.href).searchParams.get('post');
      const visible = selected ? items.filter(item => (text(item, 'guid') || text(item, 'link')) === selected) : items;
      root.replaceChildren();
      for (const item of visible) {
        const title = text(item, 'title'); const body = plainText(text(item, 'description')); const source = safeURL(text(item, 'link')); const key = text(item, 'guid') || source;
        const article = document.createElement('article'); article.className = 'card';
        const h = document.createElement('h3'); h.textContent = title; article.append(h);
        const date = new Date(text(item, 'pubDate')); if (!Number.isNaN(date.getTime())) { const time = document.createElement('time'); time.className = 'post-meta'; time.dateTime = date.toISOString(); time.textContent = date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }); article.append(time); }
        const image = safeURL(item.getElementsByTagName('enclosure')[0]?.getAttribute('url') || '');
        if (image) { const img = document.createElement('img'); img.className = 'post-image'; img.src = image; img.alt = title; img.loading = 'lazy'; img.addEventListener('error', () => img.remove(), { once: true }); article.append(img); }
        else { const label = document.createElement('p'); label.className = 'post-meta'; label.textContent = 'Text-only post'; article.append(label); }
        const p = document.createElement('p'); p.className = 'post-text'; p.textContent = body; article.append(p);
        const permalink = new URL(window.location.pathname, window.location.origin); permalink.searchParams.set('post', key);
        const shares = document.createElement('div'); shares.className = 'share-actions';
        shares.append(action('Share on Facebook', 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(permalink.href)), action('Share on LinkedIn', 'https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(permalink.href)));
        const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = 'Copy post text';
        copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(title + '\n\n' + body + '\n\n' + permalink.href); copy.textContent = 'Copied'; } catch { copy.textContent = 'Select the text above to copy'; } }); shares.append(copy); article.append(shares); root.append(article);
      }
      status.textContent = visible.length ? visible.length + (visible.length === 1 ? ' post' : ' posts') : selected ? 'This post is not in the current feed.' : 'No posts published yet.';
      if (selected) { const all = document.createElement('a'); all.href = window.location.pathname; all.textContent = 'View all posts'; status.append(' · ', all); }
    } catch { status.replaceChildren(); status.append('Posts could not be loaded. '); const a = document.createElement('a'); a.href = 'feed.xml'; a.textContent = 'Open the RSS feed'; status.append(a); }
  }
  render();
})();
