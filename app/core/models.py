from pydantic import BaseModel
from typing import Dict, List, Optional, Any, Union

class ProjectRequest(BaseModel):
    description: str

class AnalysisResponse(BaseModel):
    project_domain: str
    completeness_score: float
    needs_clarification: bool
    clarification_questions: List[str]
    extracted_context: Dict[str, Any]

class ReactFlowNodeData(BaseModel):
    label: str
    image: Optional[str] = None
    description: Optional[str] = None

class ReactFlowNode(BaseModel):
    id: str
    data: ReactFlowNodeData
    position: Dict[str, float]
    type: str = "custom"

class ReactFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None
    type: str = "default"

class DBTableField(BaseModel):
    name: str
    type: str
    primaryKey: bool = False
    foreignKey: bool = False
    references: Optional[str] = None
    unique: Optional[bool] = None
    
class DBTableNodeData(BaseModel):
    label: str
    fields: List[DBTableField]
    
class DBTableNode(BaseModel):
    id: str
    data: DBTableNodeData
    position: Dict[str, float]
    
class DBEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str = "smoothstep"
    animated: bool = True
    markerEnd: Dict[str, str] = {"type": "arrowclosed"}
    
NodeTypes = Union[ReactFlowNode, DBTableNode]

class DiagramResponse(BaseModel):
    nodes: List[NodeTypes]
    edges: List[Union[ReactFlowEdge, DBEdge]]
    metadata: Dict[str, Any]

class ArchitectureRequest(BaseModel):
    description: str
    context: Optional[Dict[str, Any]] = {}
    clarification_responses: Optional[Dict[str, str]] = None
    diagram_type: str = "architecture"

class TextArchitectureResponse(BaseModel):
    architecture: str
    domain: str
    recommendations: List[str]
    timestamp: str