(() => {
  'use strict';
  const root = document.getElementById('posts');
  const status = document.getElementById('feed-status');
  const styles = document.createElement('style');
  styles.textContent = '.post-tags{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}.post-tags a{border-radius:16px;padding:5px 10px;background:#e8f5f3;color:#083e48;text-decoration:none;font-size:13px}.post-hashtags{color:#075e66;overflow-wrap:anywhere}.caption-box{width:100%;box-sizing:border-box;min-height:230px;padding:12px;font:inherit;line-height:1.6}.share-note{font-size:13px;margin-top:10px}.share-actions{flex-wrap:wrap;gap:8px}.caption-preview{margin-top:12px}';
  document.head.append(styles);
  const tagsFor = item => [...new Set([...item.getElementsByTagName('category')].map(n => n.textContent.trim()).filter(Boolean))];
  const hashtagsFor = tags => ['#ElectroLounge', ...tags.map(t => '#' + t.replace(/[^A-Za-z0-9]/g, '')).filter(t => t.length > 1)].join(' ');
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
      const selectedTag = new URL(window.location.href).searchParams.get('tag');
      const visible = items.filter(item => (!selected || (text(item, 'guid') || text(item, 'link')) === selected) && (!selectedTag || tagsFor(item).includes(selectedTag)));
      root.replaceChildren();
      for (const item of visible) {
        const title = text(item, 'title'); const body = plainText(text(item, 'description')); const source = safeURL(text(item, 'link')); const key = text(item, 'guid') || source;
        const article = document.createElement('article'); article.className = 'card';
        const h = document.createElement('h3'); h.textContent = title; article.append(h);
        const date = new Date(text(item, 'pubDate')); if (!Number.isNaN(date.getTime())) { const time = document.createElement('time'); time.className = 'post-meta'; time.dateTime = date.toISOString(); time.textContent = date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }); article.append(time); }
        const image = safeURL(item.getElementsByTagName('enclosure')[0]?.getAttribute('url') || '');
        if (image) { const img = document.createElement('img'); img.className = 'post-image'; img.src = image; img.alt = title; img.loading = 'lazy'; img.addEventListener('error', () => img.remove(), { once: true }); const imageLink = document.createElement('a'); imageLink.href = source && source.startsWith(window.location.origin + '/electro-lounge/posts/') ? source : window.location.pathname + '?post=' + encodeURIComponent(key); imageLink.setAttribute('aria-label', 'Read ' + title); imageLink.append(img); article.append(imageLink); }
        else { const label = document.createElement('p'); label.className = 'post-meta'; label.textContent = 'Text-only post'; article.append(label); }
        const p = document.createElement('p'); p.className = 'post-text'; p.textContent = body; article.append(p);
        const permalink = source && source.startsWith(window.location.origin + '/electro-lounge/posts/') ? new URL(source) : new URL(window.location.pathname, window.location.origin); if (!permalink.pathname.includes('/posts/')) permalink.searchParams.set('post', key);
        const tags = tagsFor(item); const hashtags = hashtagsFor(tags);
        const tagList = document.createElement('div'); tagList.className = 'post-tags'; tagList.setAttribute('aria-label', 'Post topics');
        for (const tag of tags) { const tagURL = new URL(window.location.pathname, window.location.origin); tagURL.searchParams.set('tag', tag); const a = document.createElement('a'); a.href = tagURL.href; a.textContent = tag; tagList.append(a); } article.append(tagList);
        const hashLine = document.createElement('p'); hashLine.className = 'post-hashtags'; hashLine.textContent = hashtags; article.append(hashLine);
        const caption = title + '\n\n' + body + '\n\n' + hashtags;
        const preview = document.createElement('details'); preview.className = 'caption-preview'; const summary = document.createElement('summary'); summary.textContent = 'Ready-to-publish caption';
        const box = document.createElement('textarea'); box.className = 'caption-box'; box.readOnly = true; box.value = caption; box.setAttribute('aria-label', 'Full post caption without links'); preview.append(summary, box);
        const note = document.createElement('p'); note.className = 'share-note'; note.setAttribute('role', 'status'); note.textContent = 'The caption contains no links. Share opens the article image preview; paste the caption, review, then publish.';
        async function copyCaption() { try { await navigator.clipboard.writeText(caption); return true; } catch { preview.open = true; box.focus(); box.select(); return false; } }
        const shares = document.createElement('div'); shares.className = 'share-actions';
        function shareButton(platform, url) { const a = action('Copy & share on ' + platform, url); a.addEventListener('click', async event => { if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return; event.preventDefault(); window.open(url, '_blank', 'noopener,noreferrer'); const copied = await copyCaption(); note.textContent = copied ? 'Caption copied, including hashtags. In ' + platform + ', paste it with Ctrl+V (or Paste on mobile), review, then publish.' : 'Select and copy the caption below, then paste it into ' + platform + '.'; }); return a; }
        shares.append(shareButton('Facebook', 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(permalink.href)), shareButton('LinkedIn', 'https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(permalink.href)));
        const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = 'Copy full caption'; copy.addEventListener('click', async () => { const ok = await copyCaption(); note.textContent = ok ? 'Caption copied: post text, emojis and hashtags. No links included.' : 'Select and copy the caption below.'; }); shares.append(copy);
        if (image) shares.append(action('Open post image', image));
        article.append(shares, note, preview); root.append(article);
      }
      status.textContent = visible.length ? visible.length + (visible.length === 1 ? ' post' : ' posts') : selected ? 'This post is not in the current feed.' : 'No posts published yet.';
      if (selected || selectedTag) { const all = document.createElement('a'); all.href = window.location.pathname; all.textContent = 'View all posts'; status.append(' · ', all); }
    } catch { status.replaceChildren(); status.append('Posts could not be loaded. '); const a = document.createElement('a'); a.href = 'feed.xml'; a.textContent = 'Open the RSS feed'; status.append(a); }
  }
  render();
})();
