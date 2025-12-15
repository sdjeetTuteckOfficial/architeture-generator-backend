from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import os
import json
import re
from datetime import datetime
from typing import Union
import uvicorn
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from constants.constants import AWS_AVAILABLE_IMAGES, AZURE_AVAILABLE_IMAGES, local_images
load_dotenv()

# Initialize Gemini
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable not set")
os.environ["GOOGLE_API_KEY"] = google_api_key

app = FastAPI(title="Architecture Generator API", version="2.0.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:3000", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Available icons for architecture components
AVAILABLE_ICONS = AWS_AVAILABLE_IMAGES + AZURE_AVAILABLE_IMAGES + local_images

# Pydantic Models
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

# Initialize LLM
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7, max_tokens=4000)

class ArchitectureAnalyzer:
    """Core analyzer for extracting context from project descriptions"""
    
    @staticmethod
    def analyze_context(prompt: str) -> Dict[str, Any]:
        """Extract structured context from user prompt"""
        analysis_prompt = f"""
        Analyze this project description and extract key information in JSON format:
        
        "{prompt}"
        
        Extract all relevant details and return JSON with this structure:
        {{
            "project_domain": "primary domain (e-commerce, social media, fintech, healthcare, education, enterprise, etc.)",
            "project_type": "specific system type (web app, mobile app, API platform, data pipeline, AI system, etc.)",
            "project_scale": "estimated scale (startup/small/medium/large/enterprise)",
            "user_types": ["different user categories mentioned"],
            "cloud_services": ["azure, aws, gcp, etc. if specified"],
            "core_features": ["main features and functionalities"],
            "technical_stack": ["specific technologies, frameworks, languages mentioned"],
            "data_requirements": ["data types, storage needs, processing requirements"],
            "integration_needs": ["external services, APIs, third-party systems"],
            "performance_requirements": ["speed, throughput, latency requirements"],
            "security_requirements": ["authentication, authorization, compliance needs"],
            "scalability_needs": ["growth expectations, scaling requirements"],
            "deployment_environment": ["cloud providers, infrastructure preferences"],
            "business_constraints": ["budget, timeline, compliance requirements"],
            "industry_specific": ["domain-specific requirements like HIPAA, PCI-DSS, etc."],
            "complexity_indicators": {{
                "feature_count": "estimated number of major features",
                "integration_complexity": "low/medium/high based on external dependencies",
                "data_complexity": "simple/moderate/complex based on data requirements",
                "user_complexity": "single/multiple user types and permissions"
            }},
            "architectural_patterns": ["microservices, monolith, serverless, event-driven patterns suggested"],
            "estimated_team_size": "suggested team size based on complexity",
            "development_timeline": "estimated timeline based on scope"
        }}
        
        Analyze the prompt thoroughly and extract specific details. If something isn't mentioned, use empty arrays or "not specified".
        Consider the complexity and suggest appropriate architectural approaches.
        
        Be precise and extract only what's explicitly mentioned.
        """
        
        try:
            response = llm.invoke([HumanMessage(content=analysis_prompt)])
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Context analysis error: {e}")
        
        # Fallback analysis
        return {
            "project_domain": "web application",
            "project_type": "custom software system",
            "completeness_score": 0.3
        }
    
    @staticmethod
    def calculate_completeness(context: Dict[str, Any], prompt: str) -> float:
        """Calculate how complete the requirements are"""
        score = 0.0
        word_count = len(prompt.split())
        
        # Word count scoring
        if word_count > 100: score += 0.2
        elif word_count > 50: score += 0.15
        elif word_count > 20: score += 0.1
        
        # Content scoring
        if len(context.get("technologies", [])) > 0: score += 0.15
        if len(context.get("functional_requirements", [])) > 2: score += 0.15
        if len(context.get("non_functional_requirements", [])) > 1: score += 0.15
        if len(context.get("business_requirements", [])) > 0: score += 0.1
        if len(context.get("integrations", [])) > 0: score += 0.1
        if len(context.get("scale_indicators", [])) > 0: score += 0.15
        
        return min(score, 1.0)
    
    @staticmethod
    def generate_questions(context: Dict[str, Any], completeness: float) -> List[str]:
        """Generate targeted clarification questions"""
        domain = context.get("project_domain", "system")
        
        questions_prompt = f"""
        Based on this project analysis for a {domain}, generate 4-6 specific clarification questions:
        
        Context: {json.dumps(context, indent=2)}
        Completeness: {completeness:.2f}
        
        Focus on missing critical information for architecture design.
        Return a JSON array of questions: ["question1", "question2", ...]
        """
        
        try:
            response = llm.invoke([HumanMessage(content=questions_prompt)])
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Question generation error: {e}")
        
        # Fallback questions
        return [
            f"What are the key functional requirements for your {domain}?",
            "What is the expected user scale and performance requirements?",
            "Do you have specific technology preferences or constraints?",
            "What external systems need integration?",
            "What are your deployment and infrastructure preferences?"
        ]

class DiagramGenerator:
    """Generate ReactFlow diagrams for different architecture types"""
    
    @staticmethod
    def generate_architecture_diagram(description: str, context: Dict[str, Any], 
                                    user_responses: Dict[str, str]) -> Dict[str, Any]:
        """Generate comprehensive architecture diagram"""
        
        architecture_prompt = f"""
        Create a ReactFlow architecture diagram JSON for this project:
        
        Description: {description}
        Context: {json.dumps(context, indent=2)}
        User Responses: {json.dumps(user_responses, indent=2)}
        
        Generate a robust, microservices-based architecture with 15-30 components.
        Use separation of concerns and include:
        - Frontend components (React, Mobile apps)
        - API Gateway and Load Balancers  
        - Microservices (User, Auth, Payment, Notification, etc.)
        - Databases (Primary, Cache, Analytics)
        - External integrations
        - DevOps components (CI/CD, Monitoring)
        - Security components
        
        Return ONLY this JSON structure:
        {{
            "nodes": [
                {{
                    "id": "unique_id",
                    "type": "custom", 
                    "data": {{ 
                        "label": "Component Name",
                        "image": "icon.png",
                        "description": "Brief description"
                    }},
                    "position": {{ "x": 100, "y": 100 }}
                }}
            ],
            "edges": [
                {{
                    "id": "edge_id",
                    "source": "source_node", 
                    "target": "target_node",
                    "label": "API Call"
                }}
            ]
        }}
        
        Use these available icons: {AVAILABLE_ICONS}
        Position nodes in logical layers (Frontend: y=50-150, API: y=200-300, Services: y=350-500, Data: y=550-650)
        """
        
        try:
            response = llm.invoke([HumanMessage(content=architecture_prompt)])
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Architecture diagram error: {e}")
        
        # Fallback architecture
        return {
            "nodes": [
                {"id": "frontend", "type": "custom", "data": {"label": "Frontend App", "image": "react.png"}, "position": {"x": 200, "y": 50}},
                {"id": "api", "type": "custom", "data": {"label": "API Gateway", "image": "api-gateway.png"}, "position": {"x": 200, "y": 200}},
                {"id": "backend", "type": "custom", "data": {"label": "Backend Service", "image": "nodejs.png"}, "position": {"x": 200, "y": 350}},
                {"id": "database", "type": "custom", "data": {"label": "Database", "image": "postgresql.png"}, "position": {"x": 200, "y": 500}}
            ],
            "edges": [
                {"id": "fe-api", "source": "frontend", "target": "api", "label": "HTTP"},
                {"id": "api-be", "source": "api", "target": "backend", "label": "Route"},
                {"id": "be-db", "source": "backend", "target": "database", "label": "Query"}
            ]
        }
    
    @staticmethod
    def generate_database_diagram(description: str, context: Dict[str, Any], 
                                user_responses: Dict[str, str]) -> Dict[str, Any]:
        """Generate database schema diagram with React Flow compatible format"""
        
        user_prompt = f"""
        Project Description: {description}
        
        Context Information:
        {json.dumps(context, indent=2)}
        
        Additional Requirements:
        {json.dumps(user_responses, indent=2)}
        
        Based on the above information, create a comprehensive database schema with 4-8 related tables that would support this system.
        """
        
        db_prompt = f"""You are an assistant that returns React Flow-compatible database schema diagrams in JSON.

The JSON must include:
- nodes: array of objects, each representing a database table.
- edges: array of objects, representing relationships between tables.

Each node (table) object must have the following structure:
{{
  "id": "unique_table_id_lowercase_snake_case", // e.g., "users", "products"
  "data": {{
    "label": "Table Name", // e.g., "Users", "Products"
    "fields": [ // Array of column objects
      {{
        "name": "column_name", // e.g., "id", "username", "product_id"
        "type": "SQL_TYPE",    // e.g., "INT", "VARCHAR(255)", "TIMESTAMP", "BOOLEAN", "TEXT"
        "primaryKey": true/false, // true if it's a primary key
        "foreignKey": true/false, // true if it's a foreign key
        "references": "referenced_table_id.referenced_column_name" // Required if foreignKey is true, e.g., "users.id"
      }}
      // ... more field objects
    ]
  }},
  "position": {{ "x": number, "y": number }} // Coordinates for the node
}}

Each edge (relationship) object must have the following structure:
{{
  "id": "unique_edge_id", // e.g., "edge-users-orders"
  "source": "source_table_id",
  "target": "target_table_id",
  "type": "smoothstep", // Recommended for clean lines
  "animated": true,    // Recommended for visual clarity
  "markerEnd": {{ "type": "arrowclosed" }} // Recommended for direction
}}

Ensure that foreign key relationships are correctly represented by both:
1. Setting "foreignKey": true and "references": "table_id.column_name" in the field definition of the child table.
2. Creating an edge from the parent table's ID to the child table's ID (source -> target).

Generate a comprehensive database schema with 6-12 related tables based on the project requirements.
Position nodes in a logical layout with appropriate spacing (e.g., x: 0, 300, 600, 900 and y: 0, 150, 300, 450).

Return ONLY valid JSON format with both "nodes" and "edges" arrays, without markdown or code block formatting.

Now generate the database schema for:
"{user_prompt}"
"""
        
        try:
            response = llm.invoke([HumanMessage(content=db_prompt)])
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Database diagram error: {e}")
        
        # Fallback database schema
        return {
            "nodes": [
                {
                    "id": "users",
                    "data": {
                        "label": "Users",
                        "fields": [
                            {"name": "id", "type": "INT", "primaryKey": True, "foreignKey": False},
                            {"name": "email", "type": "VARCHAR(255)", "primaryKey": False, "foreignKey": False, "unique": True},
                            {"name": "username", "type": "VARCHAR(50)", "primaryKey": False, "foreignKey": False},
                            {"name": "created_at", "type": "TIMESTAMP", "primaryKey": False, "foreignKey": False}
                        ]
                    },
                    "position": {"x": 100, "y": 100}
                },
                {
                    "id": "orders",
                    "data": {
                        "label": "Orders",
                        "fields": [
                            {"name": "id", "type": "INT", "primaryKey": True, "foreignKey": False},
                            {"name": "user_id", "type": "INT", "primaryKey": False, "foreignKey": True, "references": "users.id"},
                            {"name": "order_date", "type": "TIMESTAMP", "primaryKey": False, "foreignKey": False},
                            {"name": "total_amount", "type": "DECIMAL(10,2)", "primaryKey": False, "foreignKey": False}
                        ]
                    },
                    "position": {"x": 300, "y": 100}
                }
            ],
            "edges": [
                {
                    "id": "edge-users-orders",
                    "source": "users",
                    "target": "orders",
                    "type": "smoothstep",
                    "animated": True,
                    "markerEnd": {"type": "arrowclosed"}
                }
            ]
        }

class TextArchitectureGenerator:
    """Generate detailed text-based architecture documents"""
    
    @staticmethod
    def generate_detailed_architecture(description: str, context: Dict[str, Any], 
                                     user_responses: Dict[str, str]) -> Dict[str, Any]:
        """Generate comprehensive architecture document"""
        
        domain = context.get("project_domain", "software system")
        
        arch_prompt = f"""
        You are a senior software architect. Create a comprehensive architecture document for this {domain} project:
        
        PROJECT DESCRIPTION: {description}
        CONTEXT: {json.dumps(context, indent=2)}
        ADDITIONAL REQUIREMENTS: {json.dumps(user_responses, indent=2)}
        
        Generate a detailed architecture document with these sections:
        
        1. **Executive Summary**: Project overview and key architectural decisions
        2. **System Architecture**: High-level system design and component interaction
        3. **Technology Stack**: Recommended technologies with justifications
        4. **Service Architecture**: Detailed breakdown of microservices/components
        5. **Data Architecture**: Database design, data flow, and storage strategy
        6. **Security Architecture**: Authentication, authorization, and security measures
        7. **Scalability Strategy**: Horizontal/vertical scaling approaches
        8. **Integration Architecture**: APIs, message queues, external services
        9. **Deployment Strategy**: Infrastructure, CI/CD, and deployment patterns
        10. **Monitoring & Observability**: Logging, metrics, and monitoring strategy
        11. **Performance Considerations**: Caching, optimization, and performance targets
        12. **Risk Assessment**: Technical risks and mitigation strategies
        
        Make it specific to {domain}, technically detailed, and actionable.
        Include specific technology recommendations with reasoning.
        """
        
        try:
            response = llm.invoke([HumanMessage(content=arch_prompt)])
            
            # Extract key recommendations
            rec_prompt = f"""
            Based on this architecture document, extract 5-8 key technical recommendations as a JSON array:
            
            {response.content[:2000]}...
            
            Return: ["recommendation1", "recommendation2", ...]
            """
            
            rec_response = llm.invoke([HumanMessage(content=rec_prompt)])
            json_match = re.search(r'\[.*\]', rec_response.content, re.DOTALL)
            recommendations = json.loads(json_match.group()) if json_match else []
            
            return {
                "architecture": response.content,
                "recommendations": recommendations
            }
        except Exception as e:
            print(f"Text architecture error: {e}")
            return {
                "architecture": f"Error generating architecture document: {str(e)}",
                "recommendations": []
            }

# Initialize service classes
analyzer = ArchitectureAnalyzer()
diagram_gen = DiagramGenerator()
text_gen = TextArchitectureGenerator()

# API Routes
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_project(request: ProjectRequest):
    """Analyze project and determine if clarification is needed"""
    try:
        context = analyzer.analyze_context(request.description)
        completeness = analyzer.calculate_completeness(context, request.description)
        needs_clarification = completeness < 0.6
        
        questions = []
        if needs_clarification:
            questions = analyzer.generate_questions(context, completeness)
        
        return AnalysisResponse(
            project_domain=context.get("project_domain", "software system"),
            completeness_score=completeness,
            needs_clarification=needs_clarification,
            clarification_questions=questions,
            extracted_context=context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

@app.post("/generate-diagram", response_model=DiagramResponse)
async def generate_diagram(request: ArchitectureRequest):
    """Generate ReactFlow diagram"""
    try:
        user_responses = request.clarification_responses or {}
        
        if request.diagram_type == "db_diagram":
            diagram_data = diagram_gen.generate_database_diagram(
                request.description, request.context, user_responses
            )
            # Process nodes for database type
            nodes = []
            for node_data in diagram_data["nodes"]:
                node = DBTableNode(
                    id=node_data["id"],
                    data=DBTableNodeData(
                        label=node_data["data"]["label"],
                        fields=[DBTableField(**field) for field in node_data["data"]["fields"]]
                    ),
                    position=node_data["position"]
                )
                nodes.append(node)
            
            # Process edges for database type
            edges = []
            for edge_data in diagram_data["edges"]:
                edge = DBEdge(**edge_data)
                edges.append(edge)

        else:
            diagram_data = diagram_gen.generate_architecture_diagram(
                request.description, request.context, user_responses
            )
            nodes = [ReactFlowNode(**node) for node in diagram_data["nodes"]]
            edges = [ReactFlowEdge(**edge) for edge in diagram_data["edges"]]
        
        return DiagramResponse(
            nodes=nodes,
            edges=edges,
            metadata={
                "diagram_type": request.diagram_type,
                "domain": request.context.get("project_domain", "software system"),
                "timestamp": datetime.now().isoformat(),
                "node_count": len(diagram_data["nodes"]),
                "edge_count": len(diagram_data["edges"])
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagram generation error: {str(e)}")

@app.post("/generate-text-architecture", response_model=TextArchitectureResponse)
async def generate_text_architecture(request: ArchitectureRequest):
    """Generate detailed text architecture document"""
    try:
        user_responses = request.clarification_responses or {}
        result = text_gen.generate_detailed_architecture(
            request.description, request.context, user_responses
        )
        
        return TextArchitectureResponse(
            architecture=result["architecture"],
            domain=request.context.get("project_domain", "software system"),
            recommendations=result["recommendations"],
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text architecture error: {str(e)}")

@app.get("/")
async def root():
    return {
        "message": "Robust Architecture Generator API v2.0",
        "features": [
            "Project analysis and context extraction",
            "Dynamic clarification questions",
            "ReactFlow architecture diagrams",
            "Database schema diagrams", 
            "Detailed text architecture documents"
        ],
        "available_icons": len(AVAILABLE_ICONS)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }

@app.get("/icons")
async def get_available_icons():
    """Return list of available icons for frontend"""
    return {"icons": AVAILABLE_ICONS}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)