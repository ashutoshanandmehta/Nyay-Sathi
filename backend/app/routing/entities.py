"""Mention resolution is separate from verified identity and legal authority."""

from app.resolution.planner import ChannelRegistry


class EntityResolver:
    def __init__(self, registry=None):
        self.registry = registry or ChannelRegistry()

    def candidates(self, interpretation):
        results = []
        for task in interpretation.tasks:
            for entity in task.entities:
                profile = next(
                    (
                        p
                        for p in self.registry.data["platforms"]
                        if entity.kind == "organization"
                        and entity.name.casefold() in {a.casefold() for a in p["aliases"]}
                    ),
                    None,
                )
                results.append(
                    {
                        "task_id": task.task_id,
                        "name": entity.name,
                        "kind": entity.kind,
                        "relationship_role": entity.role,
                        "identity_status": entity.identity_status,
                        "profile_id": profile["id"] if profile else None,
                        "source_url": profile["source_url"] if profile else None,
                        "profile_status": profile["verification_status"]
                        if profile
                        else "unverified_mention",
                        "authority_eligibility": "not_established",
                    }
                )
        return results
