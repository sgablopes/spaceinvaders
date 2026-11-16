// IDs exclusivamente sintéticos: nenhum vídeo real é consultado pelos testes.
const test = require('node:test');
const assert = require('node:assert/strict');
const {resolvePitch} = require('../player.js');

test('URL ausente ou insegura não cria um player', () => {
  for (const url of ['', 'not-a-url', 'javascript:alert(1)', 'http://example.com/video.mp4', 'https://user:password@example.com/video.mp4']) {
    assert.equal(resolvePitch(url), null);
  }
});

test('YouTube usa domínio de privacidade e ID explícito', () => {
  const result = resolvePitch('https://www.youtube.com/watch?v=SYNTHETIC01');
  assert.equal(result.kind, 'iframe');
  assert.equal(result.source, 'https://www.youtube-nocookie.com/embed/SYNTHETIC01?autoplay=1&rel=0');
});

test('YouTube curto e shorts mantêm a mesma identificação', () => {
  assert.equal(resolvePitch('https://youtu.be/SYNTHETIC01').source, resolvePitch('https://youtube.com/shorts/SYNTHETIC01').source);
});

test('Vimeo incorpora somente o ID numérico informado', () => {
  assert.equal(resolvePitch('https://vimeo.com/12345').source, 'https://player.vimeo.com/video/12345?autoplay=1');
});

test('Arquivo HTTPS de vídeo usa player nativo sem perder a URL', () => {
  const url = 'https://example.com/pitch.mp4?version=1';
  const result = resolvePitch(url);
  assert.equal(result.kind, 'video');
  assert.equal(result.source, url);
  assert.equal(result.original, url);
});

test('Outro domínio não é presumido incorporável', () => {
  assert.equal(resolvePitch('https://youtube.com.example.com/watch?v=SYNTHETIC01').kind, 'external');
  assert.equal(resolvePitch('https://example.com/our-pitch').kind, 'external');
});
