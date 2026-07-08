"""USGS parser: the feed's documented quirks (feeds/usgs.md)."""

from __future__ import annotations

from conftest import make_payload, make_quake

from hadr.feeds import usgs


def test_parses_basic_fields():
    payload = make_payload([make_quake(eq_id="us123", mag=6.4, alert="yellow")])
    (rec,) = usgs.parse(payload)
    assert rec.source == "usgs"
    assert rec.source_id == "us123"
    assert rec.hazard_type == "EQ"
    assert rec.mag == 6.4
    assert rec.pager == "yellow"
    assert rec.occurred_at.year == 2026  # epoch ms -> UTC datetime


def test_tolerates_utf8_bom():
    payload = make_payload([make_quake(eq_id="us1")], bom=True)
    (rec,) = usgs.parse(payload)
    assert rec.source_id == "us1"


def test_ids_split_into_aliases_excluding_preferred():
    payload = make_payload(
        [make_quake(eq_id="ci41287863", ids=",ci41287863,us6000tafd,")]
    )
    (rec,) = usgs.parse(payload)
    assert rec.source_id == "ci41287863"
    assert rec.aliases == ["us6000tafd"]


def test_non_earthquake_features_dropped():
    payload = make_payload(
        [
            make_quake(eq_id="eq1"),
            make_quake(eq_id="qb1", quake_type="quarry blast"),
        ]
    )
    recs = usgs.parse(payload)
    assert [r.source_id for r in recs] == ["eq1"]


def test_raw_ref_indexes_into_payload():
    payload = make_payload([make_quake(eq_id="a"), make_quake(eq_id="b")])
    recs = usgs.parse(payload, raw_ref="archive/x.json")
    assert recs[1].raw_ref == "archive/x.json#1"
