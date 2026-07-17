"""URL identity, output planning, and durable artifact records."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from html2md.utils.path_safety import contained_path, safe_path_segment


def canonical_url_identity(url: str) -> str:
    """Return the fragment-free normalized identity of one HTTP(S) resource."""
    parts = urlsplit(url)
    scheme = parts.scheme.casefold()
    if scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"Archive identity requires an HTTP(S) URL: {url}")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Archive URLs cannot contain credentials")
    hostname = parts.hostname.encode("idna").decode("ascii").casefold().rstrip(".")
    try:
        port = parts.port
    except ValueError as error:
        raise ValueError(f"Invalid URL port in {url}") from error
    default_port = 443 if scheme == "https" else 80
    netloc = hostname if port in {None, default_port} else f"{hostname}:{port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


@dataclass(frozen=True)
class ArtifactRecord:
    """One durable Markdown artifact and every web identity that names it."""

    requested_url: str
    final_url: str
    canonical_url: str | None
    output_path: Path

    @property
    def aliases(self) -> tuple[str, ...]:
        values = (self.requested_url, self.final_url, self.canonical_url)
        return tuple(dict.fromkeys(value for value in values if value))


class ArtifactManifest:
    """Resolve requested, redirected, and document-canonical URLs to artifacts."""

    def __init__(self) -> None:
        self._records: list[ArtifactRecord] = []
        self._aliases: dict[str, ArtifactRecord] = {}

    @property
    def records(self) -> tuple[ArtifactRecord, ...]:
        return tuple(self._records)

    def register(self, record: ArtifactRecord) -> None:
        identities = [canonical_url_identity(alias) for alias in record.aliases]
        for identity in identities:
            existing = self._aliases.get(identity)
            if existing is not None and existing.output_path != record.output_path:
                raise ValueError(f"URL identity already maps to {existing.output_path}")
        self._records.append(record)
        for identity in identities:
            self._aliases[identity] = record

    def resolve(self, url: str) -> ArtifactRecord | None:
        try:
            return self._aliases.get(canonical_url_identity(url))
        except ValueError:
            return None

    def register_alias(self, url: str, record: ArtifactRecord) -> None:
        identity = canonical_url_identity(url)
        existing = self._aliases.get(identity)
        if existing is not None and existing.output_path != record.output_path:
            raise ValueError(f"URL identity already maps to {existing.output_path}")
        self._aliases[identity] = record

    def requested_mapping(self) -> dict[str, str]:
        return {
            record.requested_url: str(record.output_path) for record in self._records
        }

    @classmethod
    def from_mapping(cls, mapping) -> "ArtifactManifest":
        manifest = cls()
        for url, path in mapping.items():
            manifest.register(ArtifactRecord(url, url, None, Path(path)))
        return manifest


class OutputPlanner:
    """Plan contained, collision-resistant Markdown output paths."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        flatten_domain: bool = False,
        flatten_all: bool = False,
        hierarchical_domains: bool = False,
    ) -> None:
        if flatten_all and (flatten_domain or hierarchical_domains):
            raise ValueError("Flatten-all cannot be combined with domain layouts")
        if flatten_domain and hierarchical_domains:
            raise ValueError("Flatten-domain cannot use hierarchical domains")
        self.root = Path(output_dir).expanduser().resolve()
        self.flatten_domain = flatten_domain
        self.flatten_all = flatten_all
        self.hierarchical_domains = hierarchical_domains

    def plan(self, url: str) -> Path:
        identity = canonical_url_identity(url)
        parts = urlsplit(identity)
        hostname = safe_path_segment(parts.netloc)
        path_parts = [
            safe_path_segment(part) for part in parts.path.split("/") if part
        ]
        leaf = path_parts[-1] if path_parts else "index"
        stem = Path(leaf).stem or "index"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
        filename = f"{safe_path_segment(stem)[:70]}-{digest}.md"

        directory = self.root
        if not self.flatten_all:
            if self.hierarchical_domains:
                for component in reversed(hostname.split(".")):
                    directory /= safe_path_segment(component)
            else:
                directory /= hostname
            if not self.flatten_domain:
                for component in path_parts[:-1]:
                    directory /= component
        output = contained_path(self.root, directory / filename)
        output.parent.mkdir(parents=True, exist_ok=True)
        return output


class ArtifactStore:
    """Write text artifacts atomically in their planned destination directory."""

    @staticmethod
    def write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
