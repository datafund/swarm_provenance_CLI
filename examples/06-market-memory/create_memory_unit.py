#!/usr/bin/env python3
"""
Market Memory Unit Generator

Creates memory units (predictions, observations) with canonical content hashing.
Canonical hashing ensures deterministic hash computation regardless of JSON key order.

Canonical hash is computed over all fields of the unit content EXCEPT the
content_hash field itself:
    json.dumps(data, sort_keys=True, separators=(',', ':')) -> SHA-256

Usage:
    python create_memory_unit.py prediction --agent "agent-alpha" --market "BTC/USD"
    python create_memory_unit.py observation --agent "agent-alpha" --market "BTC/USD" \\
        --prediction-ref <swarm_hash>
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone


def canonical_hash(data: dict) -> str:
    """Compute SHA-256 over canonical JSON representation.

    Excludes the 'content_hash' field from the hash computation.
    Uses sorted keys and compact separators for determinism.
    """
    hashable = {k: v for k, v in data.items() if k != "content_hash"}
    canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_hash(data: dict) -> bool:
    """Verify that a memory unit's content_hash is correct."""
    expected = canonical_hash(data)
    return data.get("content_hash") == expected


def create_prediction(agent_id: str, market: str, direction: str = "up",
                      confidence: float = 0.75, horizon_hours: int = 24) -> dict:
    """Create a prediction memory unit."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    unit = {
        "type": "prediction",
        "version": "1.0",
        "agent_id": agent_id,
        "market": market,
        "timestamp": now,
        "prediction": {
            "direction": direction,
            "confidence": confidence,
            "horizon_hours": horizon_hours,
            "reasoning": f"Technical analysis indicates {direction} movement "
                         f"with {confidence:.0%} confidence over {horizon_hours}h"
        },
        "metadata": {
            "model_version": "v2.1",
            "data_sources": ["price_feed", "order_book", "sentiment"],
            "features_used": 42
        }
    }
    unit["content_hash"] = canonical_hash(unit)
    return unit


def create_observation(agent_id: str, market: str, prediction_ref: str,
                       outcome: str = "correct", actual_direction: str = "up",
                       return_pct: float = 2.3) -> dict:
    """Create an observation memory unit that links to a prediction."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    unit = {
        "type": "observation",
        "version": "1.0",
        "agent_id": agent_id,
        "market": market,
        "timestamp": now,
        "prediction_ref": prediction_ref,
        "observation": {
            "outcome": outcome,
            "actual_direction": actual_direction,
            "return_pct": return_pct,
            "evaluation_timestamp": now
        },
        "metadata": {
            "evaluation_method": "price_comparison",
            "data_source": "price_feed"
        }
    }
    unit["content_hash"] = canonical_hash(unit)
    return unit


def main():
    parser = argparse.ArgumentParser(
        description="Create market memory units with canonical hashing"
    )
    subparsers = parser.add_subparsers(dest="command", help="Unit type to create")

    # Prediction subcommand
    pred = subparsers.add_parser("prediction", help="Create a prediction unit")
    pred.add_argument("--agent", default="agent-alpha", help="Agent ID")
    pred.add_argument("--market", default="BTC/USD", help="Market pair")
    pred.add_argument("--direction", default="up", choices=["up", "down"])
    pred.add_argument("--confidence", type=float, default=0.75)
    pred.add_argument("--horizon", type=int, default=24, help="Horizon in hours")
    pred.add_argument("--output", "-o", help="Output file path")

    # Observation subcommand
    obs = subparsers.add_parser("observation", help="Create an observation unit")
    obs.add_argument("--agent", default="agent-alpha", help="Agent ID")
    obs.add_argument("--market", default="BTC/USD", help="Market pair")
    obs.add_argument("--prediction-ref", required=True, help="Swarm ref of prediction")
    obs.add_argument("--outcome", default="correct", choices=["correct", "incorrect"])
    obs.add_argument("--direction", default="up", choices=["up", "down"])
    obs.add_argument("--return-pct", type=float, default=2.3)
    obs.add_argument("--output", "-o", help="Output file path")

    # Verify subcommand
    verify = subparsers.add_parser("verify", help="Verify a memory unit's hash")
    verify.add_argument("file", help="JSON file to verify")

    args = parser.parse_args()

    if args.command == "prediction":
        unit = create_prediction(
            args.agent, args.market, args.direction,
            args.confidence, args.horizon
        )
        output = json.dumps(unit, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output + "\n")
            print(f"Prediction saved to {args.output}")
        else:
            print(output)
        print(f"\nContent hash: {unit['content_hash']}")

    elif args.command == "observation":
        unit = create_observation(
            args.agent, args.market, args.prediction_ref,
            args.outcome, args.direction, args.return_pct
        )
        output = json.dumps(unit, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output + "\n")
            print(f"Observation saved to {args.output}")
        else:
            print(output)
        print(f"\nContent hash: {unit['content_hash']}")

    elif args.command == "verify":
        with open(args.file) as f:
            data = json.load(f)
        if verify_hash(data):
            print(f"PASS: Content hash verified for {args.file}")
            print(f"  Hash: {data['content_hash']}")
        else:
            expected = canonical_hash(data)
            print(f"FAIL: Content hash mismatch for {args.file}")
            print(f"  Stored:   {data.get('content_hash', '(missing)')}")
            print(f"  Expected: {expected}")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
