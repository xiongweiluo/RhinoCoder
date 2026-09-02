#!/usr/bin/env python3
"""校验第一阶段真实黄金数据 campaign 的数量、唯一性、断言和多样性。"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.collection_campaign import DEFAULT_CAMPAIGN_MANIFEST, load_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_CAMPAIGN_MANIFEST)
    args = parser.parse_args()
    campaign = load_campaign(args.manifest)
    print(
        "Collection campaign check passed "
        f"({campaign.campaign_id}: {len(campaign.tasks)} unique tasks)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
