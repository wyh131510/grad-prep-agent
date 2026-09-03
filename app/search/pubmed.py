# -*- coding: utf-8 -*-
"""PubMed 适配器（E-utilities，免费、稳定，生物医学领域）。"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import SearchHit, SourceAdapter
from ..utils import parse_year


class PubMedSource(SourceAdapter):
    id = "pubmed"
    name = "PubMed"
    langs = ("en",)

    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def search(self, query, year_from, year_to, limit):
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": min(limit, 20),
            "sort": "relevance",
            "retmode": "json",
        }
        if year_from or year_to:
            params["term"] = (
                f"({query}) AND {year_from or '1900'}:{year_to or '2100'}[pdat]"
            )
        resp = self._get(self.ESEARCH, params=params)
        ids = (resp.json().get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []
        resp2 = self._get(
            self.EFETCH,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        )
        return self._parse(resp2.text)

    def _parse(self, xml_text: str) -> list[SearchHit]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        hits: list[SearchHit] = []
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//PMID", "").strip()
            title = " ".join((art.findtext(".//ArticleTitle", "") or "").split())
            if not title:
                continue
            abstract_parts = [
                " ".join((t.text or "").split())
                for t in art.findall(".//Abstract/AbstractText")
            ]
            abstract = "\n".join(p for p in abstract_parts if p)
            authors = []
            for au in art.findall(".//AuthorList/Author"):
                last = au.findtext("LastName", "") or ""
                fore = au.findtext("ForeName", "") or ""
                authors.append(f"{fore} {last}".strip())
            year = parse_year(art.findtext(".//PubDate/Year", "") or art.findtext(".//PubDate/MedlineDate", ""))
            venue = art.findtext(".//Journal/Title", "").strip()
            doi = ""
            for aid in art.findall(".//ArticleIdList/ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text or ""
            hits.append(
                SearchHit(
                    title=title,
                    abstract=abstract,
                    authors=[a for a in authors if a],
                    year=year,
                    venue=venue,
                    doi=doi,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    extra={"pmid": pmid},
                )
            )
        return hits
