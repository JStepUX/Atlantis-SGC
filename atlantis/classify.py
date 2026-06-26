"""The 'small model' classification step.

Generates the subjective frontmatter fields the schema assigns to the small
model: chunk_type, summary, topics(+depths), aliases, goal_affinity, utility,
authority, confidence, standalone.

Two backends:

* ``KoboldClassifier``  — calls a local KoboldCPP OpenAI-compatible endpoint.
* ``StubClassifier``    — deterministic, offline; derives plausible values from
  the chunk itself so the pipeline runs end-to-end without a model (tests,
  CI, "what does the output look like?" dry runs).

Everything the model returns is validated and coerced against the schema enums;
malformed output never crashes ingest — it falls back to safe defaults.
"""

from __future__ import annotations

import json
import re
from collections import Counter

import requests

from .config import Config
from .models import Chunk
from .textutils import content_terms, slugify

CHUNK_TYPES = {"section", "definition", "procedure", "fact", "idiom", "narrative", "reference"}
UTILITIES = {"procedural", "declarative", "contextual", "orienting"}
AUTHORITIES = {"canonical", "derived", "informal", "speculative"}

_SYSTEM_PROMPT = """\
You are the classification stage of a document-ingest pipeline. You read ONE
chunk of text and return STRICT JSON metadata about it. You are domain-agnostic:
the chunk may be about jiu-jitsu, Minnesota trivia, Star Wars, a recipe, an API,
anything. Describe what is actually there. Never invent facts.

Return ONLY a JSON object (no prose, no markdown fences) with EXACTLY these keys:

{
  "chunk_type": one of ["section","definition","procedure","fact","idiom","narrative","reference"],
  "summary": "1-2 sentence answer to 'what is in this chunk?'",
  "topics": [{"topic": "kebab-case-term", "depth": 0}, ...],
  "aliases": {"term": "same-concept different name", ...},
  "goal_affinity": [{"domain": "free-text-label", "weight": 0.0}, ...],
  "utility": one of ["procedural","declarative","contextual","orienting"],
  "authority": one of ["canonical","derived","informal","speculative"],
  "confidence": 0.0,
  "standalone": true
}

Field rules:
- chunk_type: section=structural division; definition=explains what something is;
  procedure=how to do something (steps/mechanics); fact=a discrete verifiable claim;
  idiom=a saying/figure of speech; narrative=a story/account; reference=a list/table/index.
- topics: 2-6 entries, kebab-case, ordered most-specific first. depth scale:
  0=this chunk is ABOUT this topic, 1=immediate context/frame, 2=the discipline/domain,
  3=the broader field, 4=the widest category. Not every depth must be used.
- aliases: 0-4 same-concept/different-name mappings. If you have to wonder whether
  it's an alias, leave it out. Empty object {} is fine.
- goal_affinity: 1-4 {domain, weight} pairs; weight 0..1 = how strongly a chunk
  supports an agent pursuing that domain. If everything is relevant, nothing is.
- utility: procedural=HOW; declarative=WHAT; contextual=WHY-now; orienting=WHERE-in-bigger-picture.
- authority: canonical=authoritative source; derived=synthesized; informal=casual/unverified;
  speculative=theory/untested.
- confidence: epistemic reliability 0..1 (verified fact ~0.95, plausible ~0.6, hearsay ~0.3).
- standalone: true if understandable without neighbouring chunks; false if it relies
  on prior context ("as described above", dangling references).

Output JSON only."""


def _user_prompt(chunk: Chunk) -> str:
    parts = [f"Document title: {chunk.document_title}"]
    if chunk.heading:
        parts.append(f"Section heading: {chunk.heading}")
    parts.append(f"Chunk position: {chunk.index + 1} of {chunk.total}")
    parts.append("")
    parts.append("CHUNK TEXT:")
    parts.append('"""')
    parts.append(chunk.body)
    parts.append('"""')
    return "\n".join(parts)


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model response, tolerating fences."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
    if candidate is None:
        return None
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


class _Coercer:
    """Validates/coerces a raw classification dict against the schema."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def coerce(self, raw: dict, chunk: Chunk) -> dict:
        return {
            "chunk_type": self._enum(raw.get("chunk_type"), CHUNK_TYPES, "section"),
            "summary": self._summary(raw.get("summary"), chunk),
            "topics": self._topics(raw.get("topics"), chunk),
            "aliases": self._aliases(raw.get("aliases")),
            "goal_affinity": self._goal_affinity(raw.get("goal_affinity")),
            "utility": self._enum(raw.get("utility"), UTILITIES, "declarative"),
            "authority": self._enum(
                raw.get("authority"), AUTHORITIES, self.cfg.provenance.default_authority
            ),
            "confidence": self._float(
                raw.get("confidence"), self.cfg.provenance.default_confidence
            ),
            "standalone": self._bool(raw.get("standalone"), True),
        }

    @staticmethod
    def _enum(val, allowed: set[str], default: str) -> str:
        if isinstance(val, str) and val.strip().lower() in allowed:
            return val.strip().lower()
        return default

    @staticmethod
    def _float(val, default: float) -> float:
        try:
            f = float(val)
        except (TypeError, ValueError):
            return round(float(default), 3)
        return round(min(1.0, max(0.0, f)), 3)

    @staticmethod
    def _bool(val, default: bool) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() in {"true", "yes", "1"}
        return default

    @staticmethod
    def _summary(val, chunk: Chunk) -> str:
        if isinstance(val, str) and val.strip():
            return val.strip()
        # Fallback: first sentence of the body.
        first = re.split(r"(?<=[.!?])\s", chunk.body.strip(), maxsplit=1)[0]
        return first[:240] if first else (chunk.heading or chunk.document_title)

    def _topics(self, val, chunk: Chunk) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        if isinstance(val, list):
            for item in val:
                if not isinstance(item, dict):
                    continue
                topic = slugify(str(item.get("topic", "")))
                if not topic or topic in seen:
                    continue
                try:
                    depth = int(item.get("depth", 0))
                except (TypeError, ValueError):
                    depth = 0
                depth = min(4, max(0, depth))
                out.append({"topic": topic, "depth": depth})
                seen.add(topic)
                if len(out) >= 6:
                    break
        if not out:
            out = self._fallback_topics(chunk)
        return out

    def _fallback_topics(self, chunk: Chunk) -> list[dict]:
        """Derive topics from the most frequent content terms + heading."""
        topics: list[dict] = []
        seen: set[str] = set()
        if chunk.heading:
            slug = slugify(chunk.heading)
            if slug:
                topics.append({"topic": slug, "depth": 0})
                seen.add(slug)
        common = Counter(content_terms(chunk.body)).most_common(8)
        for term, _ in common:
            slug = slugify(term)
            if slug and slug not in seen:
                topics.append({"topic": slug, "depth": 0 if not topics else 1})
                seen.add(slug)
            if len(topics) >= 3:
                break
        if not topics:
            topics = [{"topic": slugify(chunk.document_slug) or "unclassified", "depth": 0}]
        return topics

    @staticmethod
    def _aliases(val) -> dict[str, str]:
        out: dict[str, str] = {}
        if isinstance(val, dict):
            for k, v in val.items():
                if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                    out[slugify(k) or k.strip()] = v.strip()
                if len(out) >= 4:
                    break
        return out

    @staticmethod
    def _goal_affinity(val) -> list[dict]:
        out: list[dict] = []
        if isinstance(val, list):
            for item in val:
                if not isinstance(item, dict):
                    continue
                domain = item.get("domain")
                if not isinstance(domain, str) or not domain.strip():
                    continue
                try:
                    weight = float(item.get("weight", 0.5))
                except (TypeError, ValueError):
                    weight = 0.5
                weight = round(min(1.0, max(0.0, weight)), 3)
                out.append({"domain": slugify(domain) or domain.strip(), "weight": weight})
                if len(out) >= 4:
                    break
        if not out:
            out = [{"domain": "general", "weight": 0.5}]
        return out


class StubClassifier:
    """Offline deterministic classifier. No model required."""

    def __init__(self, cfg: Config):
        self.coercer = _Coercer(cfg)

    def classify(self, chunk: Chunk) -> dict:
        return self.coercer.coerce({}, chunk)

    def healthcheck(self) -> tuple[bool, str]:
        return True, "stub (offline) classifier"


class KoboldClassifier:
    """KoboldCPP OpenAI-compatible classifier."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.coercer = _Coercer(cfg)
        self.url = cfg.model.base_url.rstrip("/") + "/chat/completions"
        self.session = requests.Session()

    def healthcheck(self) -> tuple[bool, str]:
        models_url = self.cfg.model.base_url.rstrip("/") + "/models"
        try:
            r = self.session.get(models_url, timeout=8)
            r.raise_for_status()
            return True, f"reachable: {self.cfg.model.base_url}"
        except requests.RequestException as e:
            return False, f"unreachable ({models_url}): {e}"

    def _call(self, chunk: Chunk) -> str:
        headers = {"Content-Type": "application/json"}
        if self.cfg.model.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.model.api_key}"
        payload = {
            "model": self.cfg.model.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(chunk)},
            ],
            "temperature": self.cfg.model.temperature,
            "max_tokens": self.cfg.model.max_tokens,
            "response_format": {"type": "json_object"},
        }
        r = self.session.post(
            self.url, headers=headers, json=payload, timeout=self.cfg.model.timeout
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]

    def classify(self, chunk: Chunk) -> dict:
        last_err = "no attempt"
        for attempt in range(self.cfg.model.retries + 1):
            try:
                content = self._call(chunk)
            except (requests.RequestException, KeyError, ValueError) as e:
                last_err = f"transport: {e}"
                continue
            raw = _extract_json(content)
            if raw is not None:
                return self.coercer.coerce(raw, chunk)
            last_err = "unparseable JSON"
        # All attempts failed -> safe deterministic defaults, flagged low-confidence.
        result = self.coercer.coerce({}, chunk)
        result["confidence"] = min(result["confidence"], 0.3)
        result["_fallback"] = last_err
        return result


def make_classifier(cfg: Config, use_stub: bool = False):
    return StubClassifier(cfg) if use_stub else KoboldClassifier(cfg)
