// The only JavaScript in the project. Pages work without it; this adds
// three small conveniences in the browser:
//
//   1. tap a highlighted word or name to see whose it is
//   2. open the story automatically when it has been written,
//      and say so when it has grown
//   3. the "Invite friends" / "Copy link" button

// ---- 1. whose word is this? ----

const credit = document.getElementById('credit');
let picked = null;

function pick(mark) {
  if (picked) picked.classList.remove('picked');
  picked = mark;
  mark.classList.add('picked');
  credit.textContent = mark.dataset.credit;
  credit.classList.add('on');
}

for (const mark of document.querySelectorAll('mark[data-credit]')) {
  mark.addEventListener('click', () => pick(mark));
  mark.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      pick(mark);
    }
  });
}

// ---- 2. watch for the story ----

const { poll, statusUrl, version } = document.body.dataset;

async function check() {
  try {
    const res = await fetch(statusUrl, { headers: { accept: 'application/json' } });
    return res.ok ? await res.json() : null;
  } catch {
    return null; // offline for a moment; try again next time
  }
}

if (poll === 'writing') {
  let tries = 0;
  const timer = setInterval(async () => {
    const status = await check();
    if (status && status.phase === 'story') {
      clearInterval(timer);
      location.reload();
    }
    if (++tries === 12) document.getElementById('slow').hidden = false;
  }, 2500);
}

if (poll === 'growing') {
  const timer = setInterval(async () => {
    const status = await check();
    if (status && status.phase === 'story' && status.version > Number(version)) {
      clearInterval(timer);
      document.getElementById('update').hidden = false;
    }
  }, 20000);
}

// ---- 3. share ----

for (const button of document.querySelectorAll('[data-share]')) {
  button.addEventListener('click', async () => {
    const url = button.dataset.share;
    try {
      if (navigator.share) {
        await navigator.share({ title: document.title, text: "Add your three words to today's story", url });
      } else {
        await navigator.clipboard.writeText(url);
        button.textContent = 'Link copied!';
      }
    } catch {
      /* share sheet closed */
    }
  });
}
