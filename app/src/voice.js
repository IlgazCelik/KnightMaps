import { WifiScan } from './wifi.js';

// Voice search: Android's built-in speech-to-text. Tap the mic to start, tap again to stop; what's said
// goes into the search bar as you speak, turned into what the room search understands.
const ONES = { zero: 0, oh: 0, o: 0, one: 1, two: 2, to: 2, too: 2, three: 3, four: 4, for: 4, five: 5, six: 6,
  seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15,
  sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19 };
const TENS = { twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90 };
// Letters as speech recognizers tend to write them (room suffixes: 107C, 163A ...)
const LETTERS = { a: 'a', ay: 'a', alpha: 'a', b: 'b', be: 'b', bee: 'b', bravo: 'b', c: 'c', see: 'c', sea: 'c',
  charlie: 'c', d: 'd', dee: 'd', delta: 'd', e: 'e', echo: 'e', f: 'f', ef: 'f', foxtrot: 'f', g: 'g', gee: 'g',
  golf: 'g', h: 'h', aitch: 'h', hotel: 'h', j: 'j', jay: 'j', juliet: 'j' };
const PLACES = [
  [/\b(women'?s|woman'?s|ladies'?|female)\b/, "women's"], [/\b(men'?s|man'?s|gents|male)\b/, "men's"],
  [/\b(bath ?rooms?|rest ?rooms?|toilets?|washrooms?|loo)\b/, 'restroom'],
  [/\b(elevators?|lifts?)\b/, 'lift'], [/\b(stairs?|stair ?ways?|stair ?wells?|steps)\b/, 'stairs'],
];
const FILLER = /\b(please|take|me|to|the|go|going|get|find|navigate|directions?|where'?s|where|is|room|number|class ?room|i|want|need|a|an|and|hey|um|uh)\b/g;

// "Take me to room one sixteen" -> "116"; "107 see" -> "107c"; "women's bathroom" -> "women's restroom"
export function spokenToQuery(text) {
  let t = ` ${text.toLowerCase().replace(/[.,!?]/g, ' ')} `;
  const places = [];
  for (const [re, word] of PLACES) if (re.test(t)) { places.push(word); t = t.replace(re, ' '); }
  if (places.length) return places.join(' ');   // a restroom / lift / stairs request

  // number words -> digits, then join neighbouring digit groups ("1 16" -> "116", "1 1 6" -> "116")
  const words = t.split(/[\s-]+/).filter(Boolean), out = [];
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (w === 'a' && words[i + 1] === 'hundred') { out.push('1'); continue; }   // "a hundred sixteen"
    if (w === 'hundred' && out.length && /^\d$/.test(out.at(-1))) {   // "one hundred (and) sixteen"
      let rest = 0, j = i + 1;
      if (words[j] === 'and') j++;
      if (TENS[words[j]] != null) { rest = TENS[words[j]]; j++; if (ONES[words[j]] != null && ONES[words[j]] < 10) { rest += ONES[words[j]]; j++; } }
      else if (ONES[words[j]] != null) { rest = ONES[words[j]]; j++; }
      out.push(String(Number(out.pop()) * 100 + rest).padStart(3, '0'));
      i = j - 1;
    } else if (TENS[w] != null) {
      const next = ONES[words[i + 1]];
      if (next != null && next > 0 && next < 10) { out.push(String(TENS[w] + next)); i++; }
      else out.push(String(TENS[w]));
    } else if (ONES[w] != null && !(w === 'o' || w === 'oh' || w === 'to' || w === 'too' || w === 'for') ) out.push(String(ONES[w]));
    else if ((w === 'o' || w === 'oh') && out.length && /^\d+$/.test(out.at(-1))) out.push('0');   // "one oh seven"
    else if (/^\d+[a-z]?$/.test(w)) out.push(w);
    else if (LETTERS[w] && out.length && /^\d+$/.test(out.at(-1))) out.push(LETTERS[w]);   // suffix after a number
    else if (!FILLER.test(` ${w} `)) out.push(w);
    FILLER.lastIndex = 0;
  }
  let q = '';
  for (const tok of out) {
    const glue = /^\d/.test(tok) && /\d$/.test(q) || /^[a-z]$/.test(tok) && /\d$/.test(q);
    q += (q && !glue ? ' ' : '') + tok;
  }
  return q.trim();
}

let stopMic = () => {};
// Stop listening (e.g. once a destination is chosen) so later speech doesn't refill the search bar.
export function stopVoice() { stopMic(); }

export function initVoice(setQuery) {
  const mic = document.getElementById('mic');
  let on = false;
  const set = state => {
    on = state;
    mic.classList.toggle('on', on);
    mic.setAttribute('aria-pressed', String(on));
    mic.setAttribute('aria-label', on ? 'Stop voice search' : 'Voice search');
  };
  stopMic = () => { if (on) { set(false); WifiScan.stopListening().catch(() => {}); } };
  WifiScan.addListener('speech', ev => {
    setQuery(spokenToQuery(ev.text));
    if (ev.stopped) set(false);   // stopped by tapping, or Android gave up (e.g. no connection)
  });
  mic.addEventListener('pointerdown', e => e.preventDefault());   // don't steal focus / open the keyboard
  mic.addEventListener('click', async () => {
    if (on) { set(false); await WifiScan.stopListening(); return; }
    set(true);
    setQuery('');
    try { await WifiScan.startListening(); }
    catch (e) { set(false); setQuery(''); document.getElementById('room-search').placeholder = e.message || 'Voice search unavailable'; }
  });
}
