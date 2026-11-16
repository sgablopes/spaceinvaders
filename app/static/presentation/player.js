'use strict';

function resolvePitch(raw) {
  if (!raw) return null;
  let url;
  try { url = new URL(raw); } catch { return null; }
  if (url.protocol !== 'https:' || url.username || url.password) return null;
  const host = url.hostname.toLowerCase();
  let id = null;
  if (host === 'youtu.be') id = url.pathname.split('/')[1];
  if (['youtube.com', 'www.youtube.com', 'm.youtube.com', 'www.youtube-nocookie.com'].includes(host)) {
    id = url.searchParams.get('v') || url.pathname.match(/^\/(?:embed|shorts)\/([^/]+)$/)?.[1];
  }
  if (id && /^[a-zA-Z0-9_-]{11}$/.test(id)) return {kind: 'iframe', source: `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`, original: url.href};
  if (['vimeo.com', 'www.vimeo.com', 'player.vimeo.com'].includes(host)) {
    const match = url.pathname.match(/^\/(?:video\/)?(\d+)\/?$/);
    if (match) return {kind: 'iframe', source: `https://player.vimeo.com/video/${match[1]}?autoplay=1`, original: url.href};
  }
  if (/\.(mp4|webm)$/i.test(url.pathname)) return {kind: 'video', source: url.href, original: url.href};
  return {kind: 'external', source: url.href, original: url.href};
}

function initPitch() {
  const frame = document.getElementById('pitch-player');
  const button = document.getElementById('pitch-play');
  const pending = document.getElementById('pitch-pending');
  const external = document.getElementById('pitch-external');
  const pitch = resolvePitch(window.AGRION_PRESENTATION?.pitchUrl);
  if (!pitch) return;
  external.href = pitch.original;
  external.hidden = false;
  pending.hidden = true;
  button.hidden = false;
  button.addEventListener('click', () => {
    if (pitch.kind === 'external') {
      external.click();
      return;
    }
    const player = document.createElement(pitch.kind === 'iframe' ? 'iframe' : 'video');
    player.src = pitch.source;
    if (pitch.kind === 'iframe') {
      player.title = document.documentElement.lang === 'en-US' ? 'AGRION pitch video' : 'Vídeo pitch do AGRION';
      player.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
      player.allowFullscreen = true;
      player.referrerPolicy = 'strict-origin-when-cross-origin';
    } else {
      player.controls = true;
      player.autoplay = true;
      player.setAttribute('aria-label', document.documentElement.lang === 'en-US' ? 'AGRION pitch video' : 'Vídeo pitch do AGRION');
    }
    frame.replaceChildren(player);
    player.focus();
  });
}

if (typeof module !== 'undefined') module.exports = {resolvePitch};
if (typeof document !== 'undefined') initPitch();
