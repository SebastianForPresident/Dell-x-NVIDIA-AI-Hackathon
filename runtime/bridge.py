"""Fixed JSON stdio adapter. The model supplies only validated tool arguments."""
import json
import os
import sys
from agent_tools import TOOL_SCHEMAS
from server.database import get_service
from server.integration import bound_tools


def main():
    if sys.argv[1:] == ['schemas']:
        print(json.dumps(TOOL_SCHEMAS))
        return
    request = json.load(sys.stdin)
    tools = bound_tools(get_service(), os.environ['CROP_INVESTIGATION_ID'])
    result = tools.invoke(request['name'], request['arguments'], request['call_id'])
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
