// Spoken instructions: three recorded clips per instruction (public/audio). Each time an instruction is
// shown, one of its three clips is picked at random and played -- the timing is the instruction change.
const CLIPS = {
  'Go straight': 'straight',
  'Turn left': 'left',
  'Turn right': 'right',
  'You have arrived': 'arrived',
};
const players = Object.fromEntries(Object.entries(CLIPS).map(([text, name]) =>
  [text, [1, 2, 3].map(i => Object.assign(new Audio(`audio/${name}_${i}.mp3`), { preload: 'auto' }))]));
let playing = null;

// Mute button (right edge, under the search bar): silences every clip; remembered between launches.
const MUTE_KEY = 'knightmapsMuted';
let muted = false;
try { muted = localStorage.getItem(MUTE_KEY) === '1'; } catch {}
const muteBtn = document.getElementById('mute');
function showMute() {
  muteBtn.classList.toggle('muted', muted);
  muteBtn.setAttribute('aria-pressed', String(muted));
  muteBtn.setAttribute('aria-label', muted ? 'Unmute directions' : 'Mute directions');
}
muteBtn.addEventListener('click', () => {
  muted = !muted;
  try { localStorage.setItem(MUTE_KEY, muted ? '1' : '0'); } catch {}
  if (muted && playing) { playing.pause(); playing.currentTime = 0; }
  showMute();
});
showMute();

export function playInstruction(text) {
  const clips = players[text];
  if (!clips || muted) return;
  if (playing) { playing.pause(); playing.currentTime = 0; }   // a new instruction cuts off the old one
  playing = clips[Math.floor(Math.random() * clips.length)];
  playing.currentTime = 0;
  playing.play().catch(() => {});   // blocked until the first tap; see below
}

// Android's web view may only allow sound after the user has touched the page: on the first tap, start
// and immediately stop every clip once so later instructions can play on their own.
function unlock() {
  for (const clips of Object.values(players)) for (const a of clips) {
    a.muted = true;
    a.play().then(() => { a.pause(); a.currentTime = 0; a.muted = false; }).catch(() => { a.muted = false; });
  }
  window.removeEventListener('pointerdown', unlock, true);
}
window.addEventListener('pointerdown', unlock, true);
