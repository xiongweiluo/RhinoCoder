import copy
import pytest
from training.c5_inventory import canonical_inventory, load_public_mcp_tools
from training.tool_schema_inventory import load_public_mcp_tools as dynamic_tools


def test_c5_inventory_normalizes_indentation_without_changing_frozen_bytes():
    original=dynamic_tools()
    linux=copy.deepcopy(original)
    for item in linux:
        lines=item["function"]["description"].splitlines()
        item["function"]["description"]=lines[0]+"\n"+"\n".join("        "+line if line else "" for line in lines[1:])
    assert canonical_inventory(linux)==load_public_mcp_tools()==original


def test_c5_inventory_rejects_any_substantive_schema_or_description_drift():
    tools=dynamic_tools()
    tools[0]["function"]["description"]+=" substantive change"
    with pytest.raises(ValueError): canonical_inventory(tools)
