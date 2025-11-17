from pydantic import BaseModel
from typing import Dict, List, Optional, Any, Union
from uuid import UUID
from datetime import datetime

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

# UPDATED: Match your actual database schema
class ThreadCreateRequest(BaseModel):
    """Schema for thread creation requests from frontend"""
    thread_name: str
    diagram_type: Optional[str] = "architecture"  # Keep for frontend, but won't be stored in DB

class ThreadBase(BaseModel):
    user_id: UUID
    thread_name: str

class ThreadCreate(ThreadBase):
    """Internal schema for thread creation - matches database fields only"""
    pass

class ThreadResponse(ThreadBase):
    """Response schema - matches your actual database Thread model"""
    thread_id: UUID
    conversation_ids: List[UUID] = []
    created_at: datetime
    
    class Config:
        from_attributes = True

class ConversationBase(BaseModel):
    thread_id: UUID
    version: int
    diagram_json: Dict[str, Any]

class ConversationCreate(ConversationBase):
    pass

class ConversationResponse(ConversationBase):
    conversation_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# REST API Models for diagram modification
class DiagramModificationRequest(BaseModel):
    """Request to update diagram via REST API"""
    thread_id: str
    diagram: Dict[str, Any]
    
    class Config:
        schema_extra = {
            "example": {
                "thread_id": "550e8400-e29b-41d4-a716-446655440000",
                "diagram": {
                    "nodes": [
                        {
                            "id": "node_1",
                            "type": "custom",
                            "position": {"x": 100, "y": 100},
                            "data": {"label": "API Gateway"}
                        }
                    ],
                    "edges": [
                        {
                            "id": "edge_1",
                            "source": "node_1",
                            "target": "node_2"
                        }
                    ],
                    "metadata": {
                        "diagram_type": "architecture",
                        "node_count": 5,
                        "edge_count": 4
                    }
                }
            }
        }

class DiagramUpdateRequest(BaseModel):
    """PATCH request to update current version's diagram"""
    thread_id: str
    diagram: Dict[str, Any]
    
    class Config:
        schema_extra = {
            "example": {
                "thread_id": "550e8400-e29b-41d4-a716-446655440000",
                "diagram": {
                    "nodes": [
                        {
                            "id": "node_1",
                            "type": "custom",
                            "position": {"x": 150, "y": 150},
                            "data": {"label": "Updated API Gateway"}
                        }
                    ],
                    "edges": [
                        {
                            "id": "edge_1",
                            "source": "node_1",
                            "target": "node_2"
                        }
                    ]
                }
            }
        }

class DiagramModificationResponse(BaseModel):
    success: bool
    message: str
    version: int
    metadata: Optional[Dict[str, Any]] = None