"""One bounded exploration session owned by the current search job."""
from __future__ import annotations

from copy import deepcopy

from aggregate_search.models import interleave_results, make_dedup_key
from aggregate_search.pagination import PageState


class Exploration:
    MAX_RESULTS = 100
    MAX_ROUNDS = 20

    def __init__(self, job):
        self.id = job.job_id
        self.keyword = job.keyword
        self.platforms = list(job.platforms)
        self.generations = dict(job.account_generations)
        self.states = {p: PageState() for p in self.platforms}
        self.results = {p: [] for p in self.platforms}
        self.owners = {}
        self.batches = []
        self.committed = set()

    def remaining(self, platform):
        return max(0, self.MAX_RESULTS - len(self.results[platform]))

    def more(self, platform):
        state = self.states[platform]
        return (len(self.batches) < self.MAX_ROUNDS and self.remaining(platform) > 0
                and (bool(state.pending) or not state.exhausted))

    def preview(self, job):
        combined = {p: self.results[p] + job.platform_results.get(p, []) for p in self.platforms}
        grouped = interleave_results(combined, platform_order=self.platforms)
        return [r for r in grouped if not any(
            make_dedup_key(s.platform, s.content_id) in self.owners for s in (r.grouped_sources or [r]))]

    def commit(self, job):
        if job.job_id in self.committed:
            return
        self.committed.add(job.job_id)
        number = len(self.batches) + 1
        added = 0
        for p in job.platforms:
            # Only checkpoints received from this worker advance pagination.
            if p in job.page_checkpoints:
                self.states[p] = job.page_states[p].model_copy(deep=True)
            for result in job.platform_results[p]:
                key = make_dedup_key(p, result.content_id)
                if key in self.owners or not self.remaining(p):
                    continue
                self.owners[key] = number
                self.results[p].append(result.model_copy(deep=True))
                added += 1
        grouped = interleave_results(self.results, platform_order=self.platforms)
        snapshot = {"job_id": job.job_id, "overall": job._compute_overall(),
                    "completed_at": job.completed_at,
                    "platforms": deepcopy(job.platforms_state)}
        batches = [{**batch, "results": []} for batch in self.batches]
        batches.append({"number": number, "results": [], **snapshot})
        for result in grouped:
            sources = result.grouped_sources or [result]
            owner = min(self.owners[make_dedup_key(s.platform, s.content_id)] for s in sources)
            batches[owner - 1]["results"].append(result)
        self.batches = batches
        job.exploration_info = self.info(job, added)
        # New versions of old content update its original batch, not the new list.
        job._final_results = batches[-1]["results"]

    def info(self, job, added):
        return {"id": self.id, "round": len(self.batches), "max_per_platform": self.MAX_RESULTS,
                "new_sources": added, "new_contents": len(self.batches[-1]["results"]),
                "page_requests": sum(t.page_requests for t in job.timings.values()),
                "duplicates": sum(t.duplicate_count for t in job.timings.values()),
                "platforms": {p: {"collected": len(self.results[p]), "has_more": self.more(p)} for p in self.platforms},
                "previous_batches": deepcopy(self.batches[:-1])}
