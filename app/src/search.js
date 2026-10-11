import { ROOMS } from './rooms.js';

// Room search under the title: type to filter the room numbers, tap one to make it the destination.
const input = document.getElementById('room-search');
const list = document.getElementById('room-list');
const norm = s => s.toLowerCase().replace(/[\s/]/g, '');
const NONE = ['nodestination', 'none', 'clear'];

let showQuery = () => {};
// Put text in the search bar and show the matching rooms (used by voice search).
export function setQuery(text) { showQuery(text); }

export function initSearch(onPick) {
  function render() {
    const q = norm(input.value);
    const matches = ROOMS.filter(r => norm(r.name).includes(q) || (r.search && norm(r.search).includes(q)))
      .sort((a, b) => norm(b.name).startsWith(q) - norm(a.name).startsWith(q));
    // "No destination" clears the choice: listed first while nothing (or "none"/"clear") is typed.
    if (!q || NONE.some(w => w.startsWith(q))) matches.unshift(null);
    list.replaceChildren(...matches.map(room => {
      const li = document.createElement('li');
      li.textContent = room ? room.name : 'No destination';
      if (!room) li.className = 'none';
      li.addEventListener('click', () => pick(room));   // a tap picks; a drag scrolls the list
      return li;
    }));
    list.hidden = !matches.length;
  }

  showQuery = text => {
    input.value = text;
    if (text) render(); else list.hidden = true;
  };

  function pick(room) {
    input.value = '';   // the chosen room shows above the search bar
    list.hidden = true;
    input.blur();
    onPick(room);
  }

  // Touching the list mustn't take focus from the search box (that would close the list).
  list.addEventListener('pointerdown', e => e.preventDefault());
  input.addEventListener('focus', render);
  input.addEventListener('input', render);
  input.addEventListener('blur', () => { list.hidden = true; });
  // Tapping elsewhere closes a list that was opened without the keyboard (by voice search).
  document.addEventListener('pointerdown', e => {
    if (!e.target.closest('#search') && document.activeElement !== input) list.hidden = true;
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const first = list.querySelector('li');
      if (first) first.click();
    }
  });
}
