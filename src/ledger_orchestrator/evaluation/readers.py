"""Readers compared by the harness. A reader proposes; only the gate admits.

Every reader returns the same ``Reading``: amounts in TND with the page each was
read on, or an abstention with its reason, plus its cost (model calls, tokens,
seconds). Model-backed readers (phase 2, D-010) implement the same interface.

``PerturbedReader`` is an instrument, not a candidate: it injects one known error
into an otherwise correct reading so that the harness measures what the gate
catches before any model is trusted with it.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import random

from ledger_orchestrator.evaluation.gate import scopes
from ledger_orchestrator.extraction.premium_annex import AnnexError, read_premiums


@dataclass
class Reading:
    proposals: dict = field(default_factory=dict)       # code -> dict(value=str TND, page=int)
    abstained: str | None = None
    perturbed: dict = field(default_factory=dict)       # code -> perturbation kind (instrument only)
    usage: dict = field(default_factory=lambda: dict(calls=0, input_tokens=0, output_tokens=0))


class DeterministicReader:
    """The production NC 26 annex reader (extraction/premium_annex.py): the baseline."""
    name = 'deterministic'

    def read(self, task, pages, config):
        try:
            records, _ = read_premiums(pages, task['year'], config['taxonomy'], config['rounding_tolerance_tnd'])
        except AnnexError as exc:
            return Reading(abstained=str(exc))
        return Reading(proposals={code: dict(value=str(r['value']), page=r['page']) for code, r in records.items()})


class AbstainReader:
    """Always abstains: the floor every reader must beat, and the proof that abstaining is never an error."""
    name = 'abstain'

    def read(self, task, pages, config):
        return Reading(abstained='never reads')


PERTURBATIONS = ('digit_swap', 'off_by_ten', 'thousand_factor', 'category_swap', 'previous_year')


class PerturbedReader:
    """A correct baseline reading with one injected error of a given kind."""

    def __init__(self, base, kind, previous_answers=None, seed=0):
        if kind not in PERTURBATIONS:
            raise ValueError(f'Unknown perturbation: {kind}')
        self.base, self.kind, self.seed = base, kind, seed
        self.previous_answers = previous_answers or {}
        self.name = f'perturbed:{kind}'

    def read(self, task, pages, config):
        reading = self.base.read(task, pages, config)
        if reading.abstained:
            return reading
        rng = random.Random(f"{self.seed}:{task['task_id']}:{self.kind}")
        proposals = {c: dict(p) for c, p in reading.proposals.items()}
        _, members = scopes(config['taxonomy'])['nonlife']
        categories = sorted(c for c in proposals if c in members and Decimal(proposals[c]['value']) >= 100)
        perturbed = {}
        if self.kind == 'previous_year':
            previous = self.previous_answers.get((task['profile_id'], task['year'] - 1))
            if not previous:
                return Reading(abstained='no previous-year answer to copy')
            for code, answer in previous.items():
                if code in proposals and answer['amount'] != proposals[code]['value']:
                    proposals[code]['value'] = answer['amount']
                    perturbed[code] = self.kind
        elif self.kind == 'category_swap':
            pairs = [(a, b) for a in categories for b in categories
                     if a < b and members[a] != members[b] and proposals[a]['value'] != proposals[b]['value']]
            if not pairs:
                return Reading(abstained='no two categories in different branches to swap')
            a, b = rng.choice(pairs)
            proposals[a]['value'], proposals[b]['value'] = proposals[b]['value'], proposals[a]['value']
            perturbed = {a: self.kind, b: self.kind}
        else:
            if not categories:
                return Reading(abstained='no category to perturb')
            code = rng.choice(categories)
            value = Decimal(proposals[code]['value'])
            if self.kind == 'off_by_ten':
                value += 10
            elif self.kind == 'thousand_factor':
                value *= 1000
            else:
                digits = str(int(value))
                swaps = [i for i in range(len(digits) - 1) if digits[i] != digits[i + 1]]
                if not swaps:
                    return Reading(abstained='no adjacent distinct digits')
                i = rng.choice(swaps)
                value = Decimal(digits[:i] + digits[i + 1] + digits[i] + digits[i + 2:])
            proposals[code]['value'] = str(value)
            perturbed = {code: self.kind}
        if not perturbed:
            return Reading(abstained='perturbation changed nothing')
        return Reading(proposals=proposals, perturbed=perturbed, usage=reading.usage)
