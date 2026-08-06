from pydantic import BaseModel


class FlowNode(BaseModel):
    id: str
    label: str
    file_path: str
    function_name: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    depth: int                   # depth in the call tree
    node_type: str = "function"  # "function" | "method" | "entrypoint" | "exit"
    description: str | None = None


class FlowEdge(BaseModel):
    source: str
    target: str
    call_type: str = "direct"    # "direct" | "conditional" | "async" | "recursive"
    condition: str | None = None


class FlowResponse(BaseModel):
    session_id: str
    entry_point: str
    nodes: list[FlowNode]
    edges: list[FlowEdge]
    total_steps: int
    max_depth: int
    has_cycles: bool
    cycle_nodes: list[str]
