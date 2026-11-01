"""Phase 2: a tool-using model reader. The model proposes; the identity gate disposes.

The agent receives one company-year: the report's pages behind four tools and the
profile's category codes with their header aliases. It never sees the answer key.

- ``search_pages(query)``: pages whose text contains every query word;
- ``read_page(page, start_row)``: 25 rows of a page, words placed by their x
  position so that columns, blanks and dashes stay aligned;
- ``check(proposals)``: the same identity gate the harness applies, with its
  reasons, so the agent can correct a reading or decide to abstain;
- ``submit(proposals)`` / ``abstain(reason)``: the final answer.

Decision D-010 governs what leaves the machine: only page text of the published
report. Every call is recorded under the hash of its request (provider, model,
messages, tools, parameters) with the response, latency and token usage, and a
benchmark can be replayed from the recording without any network or quota. The
API key comes from ``GROQ_API_KEY`` or a git-ignored ``.env``; it is never logged
or recorded.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from ledger_orchestrator.evaluation.gate import DocumentIndex, LIFE_PREFIX, verify_premiums
from ledger_orchestrator.evaluation.readers import Reading
from ledger_orchestrator.extraction.core import lines, normalize

PROVIDERS = {'groq': dict(url='https://api.groq.com/openai/v1', key='GROQ_API_KEY')}
ROWS_PER_READ = 15
COLUMNS = 170           # characters used to lay out one page row
MAX_TURNS = 16
# Free tiers cap tokens per minute per request (Groq: 8,000 including max_tokens). About 4.5
# characters per token on these pages, so 20,000 characters of messages leave room for the answer.
CONTEXT_CHARS = 20_000
KEEP_RECENT_RESULTS = 3
MAX_TOKENS_PER_TASK = 80_000
MAX_RESPONSE_BYTES = 2_000_000


class ProviderError(RuntimeError):
    pass


class ReplayMissing(RuntimeError):
    """Replay mode found no recording for a request: the run is not reproducible."""


def api_key(provider, env_file=Path('.env')):
    name = PROVIDERS[provider]['key']
    value = os.getenv(name, '').strip()
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.strip().startswith(name + '='):
                value = line.split('=', 1)[1].strip().strip('"\'')
    if not value:
        raise ProviderError(f'{name} is not set (environment variable or git-ignored .env)')
    return value


def _urllib_transport(url, payload, headers, timeout=120):
    """POST (or GET when payload is None); returns (status, headers, body)."""
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(url, data=data, headers=headers, method='GET' if payload is None else 'POST')
    try:
        with build_opener().open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read(MAX_RESPONSE_BYTES + 1)
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f'Provider unreachable: {type(exc).__name__}') from exc


class ChatClient:
    """OpenAI-compatible chat completions (Groq), with rate-limit waits and pacing."""

    def __init__(self, provider, model, key=None, transport=None, sleep=time.sleep, min_interval=2.0,
                 max_retries=6):
        if provider not in PROVIDERS:
            raise ValueError(f'Unknown provider: {provider}')
        if not model or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', model):
            raise ValueError('A model identifier is required (see: evaluation models)')
        self.provider, self.model = provider, model
        self.url = PROVIDERS[provider]['url']
        self._key = key
        self.transport = transport or _urllib_transport
        self.sleep, self.min_interval, self.max_retries = sleep, min_interval, max_retries
        self._last = 0.0

    def _headers(self):
        if self._key is None:
            self._key = api_key(self.provider)
        # An explicit User-Agent: Groq's edge rejects urllib's default one (Cloudflare error 1010).
        return {'Authorization': f'Bearer {self._key}', 'Content-Type': 'application/json',
                'User-Agent': 'ledger-orchestrator/0.1'}

    def models(self):
        status, _, body = self.transport(self.url + '/models', None, self._headers())
        if status != 200:
            detail = body[:200].decode('utf-8', 'replace').replace(self._key or '\0', '<key>')
            raise ProviderError(f'Model list failed with HTTP {status}: {detail}')
        return sorted(m['id'] for m in json.loads(body)['data'])

    def complete(self, payload):
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            status, headers, body = self.transport(self.url + '/chat/completions', payload, self._headers())
            if status == 429 and attempt < self.max_retries:
                headers = {k.lower(): v for k, v in headers.items()}
                try:
                    delay = float(headers.get('retry-after', 0))
                except ValueError:
                    delay = 0
                self.sleep(min(max(delay, 2.0 * (attempt + 1)), 90))
                continue
            if len(body) > MAX_RESPONSE_BYTES:
                raise ProviderError('Provider response too large')
            if status != 200:
                detail = body[:300].decode('utf-8', 'replace')
                raise ProviderError(f'HTTP {status} from {self.provider}: {detail}')
            return json.loads(body)
        raise ProviderError('Rate limit persisted after retries')


class CallRecorder:
    """Content-addressed recording of model calls: ``record`` reuses or stores, ``replay`` never calls."""

    def __init__(self, directory, mode='record'):
        if mode not in ('record', 'replay'):
            raise ValueError('Recorder mode is record or replay')
        self.directory, self.mode = Path(directory), mode
        self.hits = self.misses = 0

    @staticmethod
    def request_key(request):
        canonical = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    def call(self, request, perform):
        key = self.request_key(request)
        path = self.directory / f'{key}.json'
        if path.is_file():
            self.hits += 1
            return json.loads(path.read_text(encoding='utf-8'))['response'], True
        if self.mode == 'replay':
            raise ReplayMissing(f'No recording for request {key[:12]}')
        self.misses += 1
        start = time.monotonic()
        response = perform()
        self.directory.mkdir(parents=True, exist_ok=True)
        record = dict(request=request, response=response, latency_seconds=round(time.monotonic() - start, 3),
                      recorded_at=datetime.now(timezone.utc).isoformat())
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
        return response, False


def page_rows(page, columns=COLUMNS, widest=300):
    """Each PDF row as one text line, words placed at their x position (columns stay aligned).

    The layout widens, up to ``widest`` characters, until the densest row fits
    without pushing words out of their columns (dense annexes such as ASTREE's).
    """
    result = []
    width = float(page.get('width') or 600)
    rows = lines(page.get('words', []))
    needed = max([(len(a['text']) + 1) / max(b['x0'] - a['x0'], 1.0)
                  for row in rows for a, b in zip(row, row[1:])] or [0])
    scale = min(max(columns / width, needed), widest / width)
    for row in rows:
        line = ''
        for word in row:
            start = max(int(word['x0'] * scale), len(line) + (1 if line else 0))
            line = line.ljust(start) + word['text']
        result.append(line.rstrip())
    return result


TOOLS = [
    dict(type='function', function=dict(
        name='search_pages', description='Rank pages by how many words of the query they contain (accents and case ignored).',
        parameters=dict(type='object', properties=dict(query=dict(type='string')), required=['query']))),
    dict(type='function', function=dict(
        name='read_page', description=f'Read {ROWS_PER_READ} rows of a page from start_row, columns aligned by position.',
        parameters=dict(type='object', properties=dict(page=dict(type='integer'), start_row=dict(type='integer')),
                        required=['page']))),
    dict(type='function', function=dict(
        name='find_rows', description='Return only the rows of a page that contain any of the words (e.g. '
                                      '"categories primes emises"), aligned exactly as read_page shows them.',
        parameters=dict(type='object', properties=dict(page=dict(type='integer'), words=dict(type='string')),
                        required=['page', 'words']))),
    dict(type='function', function=dict(
        name='check', description='Run the identity gate on proposed amounts and return what it admits and why.',
        parameters=dict(type='object', properties=dict(proposals=dict(
            type='object', description='code -> {"value": amount in TND, "page": page number}')),
            required=['proposals']))),
    dict(type='function', function=dict(
        name='submit', description='Final answer: the proposals you stand behind.',
        parameters=dict(type='object', properties=dict(proposals=dict(type='object')), required=['proposals']))),
    dict(type='function', function=dict(
        name='abstain', description='Give up on this report, with the reason.',
        parameters=dict(type='object', properties=dict(reason=dict(type='string')), required=['reason']))),
]


def codes_table(taxonomy):
    nonlife = taxonomy['nonlife']['aliases']
    subtotals = set(taxonomy['nonlife'].get('subtotals', {}))
    rows = [f'- {code}: header like {" / ".join(names)}' for code, names in nonlife.items()
            if code != 'TOTAL' and code not in subtotals]
    rows.append('- TOTAL_NONVIE: the TOTAL column of the non-life annex (acceptations included)')
    rows += [f'- {LIFE_PREFIX}{code}: life annex header like {" / ".join(names)}'
             for code, names in taxonomy['life']['aliases'].items() if code != 'TOTAL']
    rows.append('- TOTAL_VIE: total life issued premiums')
    return '\n'.join(rows)


SYSTEM = """You read a Tunisian insurer's published annual report ({company}, financial year {year}).
Goal: the gross issued premiums ("Primes émises", before reinsurance, net of cancellations) of year {year}
for each category, read from the regulated annexes:
- annex 13 "Résultat technique par catégorie d'assurance non-vie": one column per category, row "Primes émises";
- annex 12 (life), same structure; and the technical statements, where row PRNV11 (non-life) or
  PRV11 (life) prints the same totals.
Codes you may fill (only these; most insurers print only some of these categories):
{codes}
Rules:
- Fill the codes whose column you actually see. A category this insurer does not print is simply left out:
  do not search for it. Annex numbers are often not printed; look for the titles instead.
- Read only year {year}'s column; never the previous year's comparative or the "Primes acquises" row.
- Values are in TND. If the annex is in thousands of dinars with three decimals (e.g. 84 404,579),
  multiply by 1000 exactly. A dash in a category column is 0.
- "page" is the page where you read the amount (the annex page for categories).
- Rows keep the printed horizontal positions: an amount sits under its own header. A category with
  nothing printed under its header (blank or dash) is 0, and the next amount belongs to the next
  header, never to the empty one. Count positions, not the order of the numbers.
- Use check before submit. If the gate rejects a reading, fix it or abstain; never guess.
- Your context is small: older page reads are elided. read_page once to orient yourself, then prefer
  find_rows (e.g. words "categories primes emises") to get the header and amount rows together.
  As soon as you have read amounts, call check with every code found so far; check arguments stay
  in the conversation and serve as your notes.
Use the tools; answer only through submit or abstain."""


def _first_line(page, width=100):
    return ' '.join((page.get('text', '').strip().splitlines() or [''])[0].split())[:width]


def contents(pages):
    """A table of contents: each page's first line, so the model navigates instead of guessing queries."""
    return '\n'.join(f'p{p["page"]}: {_first_line(p) or "(no text)"}' for p in pages)


def _decimal(value):
    try:
        number = Decimal(str(value).replace(' ', '').replace(' ', ''))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def clean_proposals(raw, known):
    """Keep well-formed proposals for known codes: decimal amount (TND) and integer page."""
    if not isinstance(raw, dict):
        return {}, ['proposals must be an object of code -> {value, page}']
    result, problems = {}, []
    for code, item in raw.items():
        if code not in known:
            problems.append(f'unknown code {code}')
            continue
        value = _decimal(item.get('value')) if isinstance(item, dict) else None
        page = item.get('page') if isinstance(item, dict) else None
        if value is None or type(page) is not int:
            problems.append(f'{code}: needs a numeric value and an integer page')
            continue
        result[code] = dict(value=format(value.normalize(), 'f') if value != value.to_integral_value()
                            else str(int(value)), page=page)
    return result, problems


def fit_context(messages, budget=CONTEXT_CHARS, keep=KEEP_RECENT_RESULTS):
    """Elide the oldest large tool results (in place) until the conversation fits the budget.

    The system prompt, the table of contents, the model's own calls (including its check
    arguments), every check verdict and the latest ``keep`` tool results are never elided.
    Returns the elided count."""
    def size():
        return sum(len(m.get('content') or '') + len(json.dumps(m.get('tool_calls') or '')) for m in messages)
    calls = {c['id']: c['function'] for m in messages if m['role'] == 'assistant' for c in m.get('tool_calls') or []}
    results = [m for m in messages if m['role'] == 'tool']
    elided = 0
    for message in results[:max(len(results) - keep, 0)]:
        if size() <= budget:
            break
        function = calls.get(message.get('tool_call_id'), {})
        # The gate's verdicts are the agent's feedback signal: never elided.
        if function.get('name') == 'check' or message['content'].startswith('[elided') or len(message['content']) < 300:
            continue
        message['content'] = (f'[elided to fit the context budget: {function.get("name", "tool")} '
                              f'{function.get("arguments", "")}; call it again if needed]')
        elided += 1
    return elided


@dataclass
class _Task:
    pages: list
    index: DocumentIndex
    config: dict


class ModelReader:
    """An agent loop over the report's pages; every call goes through the recorder."""

    def __init__(self, client, recorder, temperature=0, max_turns=MAX_TURNS):
        self.client, self.recorder = client, recorder
        self.temperature, self.max_turns = temperature, max_turns
        self.name = f'{client.provider}:{client.model}'

    def _tool(self, name, arguments, task):
        pages = {p['page']: p for p in task.pages}
        if name == 'search_pages':
            words = list(dict.fromkeys(normalize(str(arguments.get('query', ''))).split()))
            scored = [(sum(w in normalize(p.get('text', '')) for w in words), p) for p in task.pages]
            scored = sorted((s for s in scored if s[0] and s[0] >= len(words) / 2), key=lambda s: -s[0])
            return [dict(page=p['page'], matched=f'{n}/{len(words)}', first_line=_first_line(p))
                    for n, p in scored[:8]] or 'no page matches'
        if name == 'read_page':
            page = pages.get(arguments.get('page'))
            if page is None:
                return f'no page {arguments.get("page")}; pages are 1..{len(task.pages)}'
            rows = page_rows(page)
            start = max(int(arguments.get('start_row') or 0), 0)
            text = '\n'.join(f'{i:>3} {r}' for i, r in enumerate(rows[start:start + ROWS_PER_READ], start))
            return f'page {page["page"]} ({page["method"]}), rows {start}-{min(start + ROWS_PER_READ, len(rows)) - 1} of {len(rows)}\n{text}'
        if name == 'find_rows':
            page = pages.get(arguments.get('page'))
            words = normalize(str(arguments.get('words', ''))).split()
            if page is None or not words:
                return f'needs a page in 1..{len(task.pages)} and some words'
            rows = page_rows(page)
            found = [f'{i:>3} {r}' for i, r in enumerate(rows) if any(w in normalize(r) for w in words)]
            return (f'page {page["page"]}, {len(found)} of {len(rows)} rows\n' + '\n'.join(found[:12])
                    if found else 'no row matches')
        if name == 'check':
            proposals, problems = clean_proposals(arguments.get('proposals'), self._known(task.config))
            verdict = verify_premiums(proposals, task.index, task.config['taxonomy'], task.config['rounding_tolerance_tnd'])
            return dict(problems=problems, decisions={c: dict(admitted=d['admitted'], reasons=sorted(set(d['reasons'])))
                                                      for c, d in verdict['decisions'].items()})
        return f'unknown tool {name}'

    @staticmethod
    def _known(config):
        taxonomy = config['taxonomy']
        subtotals = set(taxonomy['nonlife'].get('subtotals', {}))
        nonlife = {c for c in taxonomy['nonlife']['aliases'] if c != 'TOTAL' and c not in subtotals}
        life = {LIFE_PREFIX + c for c in taxonomy['life']['aliases'] if c != 'TOTAL'}
        return nonlife | life | {'TOTAL_NONVIE', 'TOTAL_VIE'}

    def read(self, task, pages, config):
        state = _Task(pages, DocumentIndex(pages), config)
        messages = [dict(role='system', content=SYSTEM.format(company=task['company'], year=task['year'],
                                                               codes=codes_table(config['taxonomy']))),
                    dict(role='user', content=f'The report has {len(pages)} pages; first line of each:\n'
                                              f'{contents(pages)}\nFind the annexes and fill the codes.')]
        usage = dict(calls=0, input_tokens=0, output_tokens=0, recorded=0, elided=0)
        seen = set()
        for _ in range(self.max_turns):
            usage['elided'] += fit_context(messages)
            payload = dict(model=self.client.model, messages=messages, tools=TOOLS, tool_choice='auto',
                           temperature=self.temperature, max_tokens=2048)
            request = dict(provider=self.client.provider, payload=payload)
            try:
                response, recorded = self.recorder.call(request, lambda: self.client.complete(payload))
            except ProviderError as exc:
                return Reading(abstained=f'provider error: {exc}', usage=usage)
            usage['calls'] += 1
            usage['recorded'] += recorded
            usage['input_tokens'] += response.get('usage', {}).get('prompt_tokens', 0)
            usage['output_tokens'] += response.get('usage', {}).get('completion_tokens', 0)
            if usage['input_tokens'] + usage['output_tokens'] > MAX_TOKENS_PER_TASK:
                return Reading(abstained='token budget exhausted', usage=usage)
            message = response['choices'][0]['message']
            calls = message.get('tool_calls') or []
            messages.append({k: v for k, v in message.items() if k in ('role', 'content', 'tool_calls') and v is not None})
            if not calls:
                messages.append(dict(role='user', content='Answer only through the tools.'))
                continue
            for call in calls:
                name = call['function']['name']
                try:
                    arguments = json.loads(call['function'].get('arguments') or '{}')
                except json.JSONDecodeError:
                    arguments = None
                if not isinstance(arguments, dict):
                    result = 'arguments must be a JSON object'
                elif name == 'submit':
                    proposals, _ = clean_proposals(arguments.get('proposals'), self._known(config))
                    return Reading(proposals=proposals, usage=usage) if proposals else Reading(
                        abstained='submitted nothing usable', usage=usage)
                elif name == 'abstain':
                    return Reading(abstained=f"model: {str(arguments.get('reason', ''))[:300]}", usage=usage)
                else:
                    result = self._tool(name, arguments, state)
                content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                signature = (name, json.dumps(arguments, sort_keys=True))
                if name != 'check' and signature in seen:
                    # Re-reading what was elided is the thrashing pattern: point the model at its notes.
                    content = ('NOTE: you already made this call. Record the amounts you read with check '
                               'now; check verdicts are never elided.\n' + content)
                seen.add(signature)
                messages.append(dict(role='tool', tool_call_id=call['id'], content=content))
        return Reading(abstained='turn budget exhausted', usage=usage)
