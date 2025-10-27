# diagram_generator.py
import json
import re
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import os

from constants.constants import AWS_AVAILABLE_IMAGES, AZURE_AVAILABLE_IMAGES, local_images

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7, max_tokens=4000)

AVAILABLE_ICONS = AWS_AVAILABLE_IMAGES + AZURE_AVAILABLE_IMAGES + local_images

class DiagramGenerator:
    """Generate ReactFlow diagrams for different architecture types"""
    
    def generate_architecture_diagram(self, description: str, context: Dict[str, Any], 
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
    
    def generate_database_diagram(self, description: str, context: Dict[str, Any], 
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
            "id": "unique_table_id_lowercase_snake_case",
            "data": {{
                "label": "Table Name",
                "fields": [
                    {{
                        "name": "column_name",
                        "type": "SQL_TYPE",
                        "primaryKey": true/false,
                        "foreignKey": true/false,
                        "references": "referenced_table_id.referenced_column_name"
                    }}
                ]
            }},
            "position": {{ "x": number, "y": number }}
        }}

        Each edge (relationship) object must have the following structure:
        {{
            "id": "unique_edge_id",
            "source": "source_table_id",
            "target": "target_table_id",
            "type": "smoothstep",
            "animated": true,
            "markerEnd": {{ "type": "arrowclosed" }}
        }}

        Ensure that foreign key relationships are correctly represented by both:
        1. Setting "foreignKey": true and "references": "table_id.column_name" in the field definition of the child table.
        2. Creating an edge from the parent table's ID to the child table's ID (source -> target).

        Generate a comprehensive database schema with 20-50 related tables based on the project requirements.
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