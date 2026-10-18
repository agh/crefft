const form = document.querySelector('#search-form');
const query = document.querySelector('#query');
const status = document.querySelector('#status');
const results = document.querySelector('#results');
const more = document.querySelector('#more');
if (!form || !query || !status || !results || !more) throw new Error('Search markup is incomplete');
form.hidden = false;
let request = 0;
let index;
let matches = [];
let shown = 0;

async function showResults(current) {
  more.hidden = true;
  const batch = await Promise.all(matches.slice(shown, shown + 5).map((result) => result.data()));
  if (current !== request) return;
  for (const page of batch) {
    const url = new URL(page.url, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/guides/')) {
      throw new Error('Unexpected search-result URL');
    }
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = url.href;
    link.textContent = page.meta.title;
    const excerpt = document.createElement('p');
    excerpt.textContent = page.plain_excerpt;
    item.append(link, excerpt);
    results.append(item);
  }
  shown += batch.length;
  status.textContent = `${matches.length} results. Showing ${shown}.`;
  more.hidden = shown >= matches.length;
}

function failure(error, current) {
  if (current !== request) return;
  index = undefined;
  results.replaceChildren();
  more.hidden = true;
  status.textContent = 'Search could not load. Browse the guide index or try again.';
  console.error('Search failed', error);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const current = ++request;
  results.replaceChildren();
  more.hidden = true;
  if (!query.value.trim()) {
    status.textContent = 'Enter search terms.';
    return;
  }
  status.textContent = 'Searching...';
  shown = 0;
  try {
    index ??= import('/pagefind/pagefind.js');
    const pagefind = await index;
    const found = await pagefind.search(query.value.trim());
    if (current !== request) return;
    matches = found.results;
    await showResults(current);
  } catch (error) {
    failure(error, current);
  }
});
more.addEventListener('click', async () => {
  const current = request;
  try {
    await showResults(current);
  } catch (error) {
    failure(error, current);
  }
});
