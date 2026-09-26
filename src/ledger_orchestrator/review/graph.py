"""Durable human-review workflow. Decisions never mutate the source workbook."""

from __future__ import annotations

import operator
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt


CHOICES = ('documented', 'follow_up')


class ReviewState(TypedDict):
    case: dict
    decisions: Annotated[list[dict], operator.add]


def ask_reviewer(state: ReviewState) -> dict:
    """Pause before each human decision; resumption adds an immutable history item."""
    answer = interrupt({
        'kind': 'financial_cell_review',
        'case': state['case'],
        'choices': list(CHOICES),
        'instruction': 'Documenter la revue ou signaler un suivi nécessaire. Aucune valeur Excel ne sera modifiée.',
    })
    if not isinstance(answer, dict) or answer.get('action') not in CHOICES:
        raise ValueError('Invalid review action')
    reviewer = answer.get('reviewer')
    note = answer.get('note')
    if not isinstance(reviewer, str) or not 2 <= len(reviewer.strip()) <= 80:
        raise ValueError('Reviewer name must contain 2–80 characters')
    if not isinstance(note, str) or not 3 <= len(note.strip()) <= 1000:
        raise ValueError('Review note must contain 3–1000 characters')
    return {'decisions': [{
        'action': answer['action'],
        'reviewer': reviewer.strip(),
        'note': note.strip(),
        'at': datetime.now(timezone.utc).isoformat(),
    }]}


def build_graph(checkpointer):
    builder = StateGraph(ReviewState)
    builder.add_node('human_review', ask_reviewer)
    builder.add_edge(START, 'human_review')
    builder.add_edge('human_review', 'human_review')
    return builder.compile(checkpointer=checkpointer)


class ReviewWorkflow:
    """Serialize SQLite-backed graph calls within the local API process."""

    def __init__(self, database: Path):
        database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database, check_same_thread=False)
        self.graph = build_graph(SqliteSaver(self.connection))
        self.lock = threading.RLock()

    @staticmethod
    def _config(case_id: str):
        return {'configurable': {'thread_id': case_id}}

    def _snapshot(self, case_id: str):
        saved = self.graph.get_state(self._config(case_id))
        values = saved.values or {}
        decisions = values.get('decisions', [])
        return {
            'started': bool(values),
            'waiting_for_human': 'human_review' in saved.next,
            'decision': decisions[-1] if decisions else None,
            'history': decisions,
        }

    def snapshot(self, case_id: str):
        with self.lock:
            return self._snapshot(case_id)

    def start(self, case_id: str, case: dict):
        with self.lock:
            existing = self.graph.get_state(self._config(case_id))
            if existing.values:
                if existing.values.get('case') != case:
                    raise ValueError('The review case changed after its checkpoint was created')
            else:
                result = self.graph.invoke({'case': case, 'decisions': []}, self._config(case_id))
                if '__interrupt__' not in result:
                    raise RuntimeError('Review graph did not pause for human input')
            return self._snapshot(case_id)

    def decide(self, case_id: str, decision: dict):
        with self.lock:
            current = self._snapshot(case_id)
            if not current['started'] or not current['waiting_for_human']:
                raise ValueError('Start this review case before recording a decision')
            result = self.graph.invoke(Command(resume=decision), self._config(case_id))
            if '__interrupt__' not in result:
                raise RuntimeError('Review graph did not pause after the decision')
            return self._snapshot(case_id)

    def close(self):
        with self.lock:
            self.connection.close()
