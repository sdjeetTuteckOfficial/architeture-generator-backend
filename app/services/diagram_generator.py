import json
import re
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import os
from datetime import datetime

from constants.constants import AWS_AVAILABLE_IMAGES, AZURE_AVAILABLE_IMAGES, local_images

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.7, max_tokens=4000)

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
                    "type": "default",
                    "label": "API Call"
                }}
            ],
            "metadata": {{
                "domain": "inferred_domain",
                "timestamp": "YYYY-MM-DDTHH:MM:SS.ssssss",
                "edge_count": number,
                "node_count": number,
                "diagram_type": "architecture"
            }}
        }}
        
        Use these available icons: {AVAILABLE_ICONS}
        Position nodes in logical layers (Frontend: y=50-150, API: y=200-300, Services: y=350-500, Data: y=550-650)
        Infer the domain (e.g., e-commerce, healthcare) from the description.
        Set timestamp to current UTC time.
        """
        
        try:
            response = llm.invoke([HumanMessage(content=architecture_prompt)])
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                diagram = json.loads(json_match.group())
                # Ensure metadata is present
                if "metadata" not in diagram:
                    diagram["metadata"] = {
                        "domain": context.get("domain", "unknown"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "edge_count": len(diagram.get("edges", [])),
                        "node_count": len(diagram.get("nodes", [])),
                        "diagram_type": "architecture"
                    }
                return diagram
        except Exception as e:
            print(f"Architecture diagram error: {e}")
        
        # Fallback JSON
        return {
            "nodes": [
                {
                    "id": "frontend_react",
                    "type": "custom",
                    "data": {
                        "label": "React Frontend",
                        "image": "React.png",
                        "description": "Web interface for users"
                    },
                    "position": {"x": 100, "y": 100}
                },
                {
                    "id": "frontend_mobile",
                    "type": "custom",
                    "data": {
                        "label": "Mobile App Frontend",
                        "image": "user.png",
                        "description": "Mobile interface for users (iOS/Android)"
                    },
                    "position": {"x": 300, "y": 100}
                },
                {
                    "id": "api_gateway",
                    "type": "custom",
                    "data": {
                        "label": "API Gateway",
                        "image": "Amazon-API-Gateway.svg",
                        "description": "Entry point for all API requests"
                    },
                    "position": {"x": 200, "y": 250}
                },
                {
                    "id": "load_balancer",
                    "type": "custom",
                    "data": {
                        "label": "Load Balancer",
                        "image": "Elastic-Load-Balancing.svg",
                        "description": "Distributes traffic across microservice instances"
                    },
                    "position": {"x": 400, "y": 250}
                },
                {
                    "id": "user_service",
                    "type": "custom",
                    "data": {
                        "label": "User Service",
                        "image": "AWS-IAM-Identity-Center.svg",
                        "description": "Manages user accounts and profiles"
                    },
                    "position": {"x": 100, "y": 400}
                },
                {
                    "id": "auth_service",
                    "type": "custom",
                    "data": {
                        "label": "Authentication Service",
                        "image": "Amazon-Cognito.svg",
                        "description": "Handles user authentication and authorization"
                    },
                    "position": {"x": 250, "y": 400}
                },
                {
                    "id": "product_service",
                    "type": "custom",
                    "data": {
                        "label": "Product Service",
                        "image": "Amazon-Elastic-Container-Service.svg",
                        "description": "Manages product catalog and details"
                    },
                    "position": {"x": 400, "y": 400}
                },
                {
                    "id": "cart_service",
                    "type": "custom",
                    "data": {
                        "label": "Cart Service",
                        "image": "Amazon-Elastic-Container-Service.svg",
                        "description": "Manages user shopping carts"
                    },
                    "position": {"x": 550, "y": 400}
                },
                {
                    "id": "order_service",
                    "type": "custom",
                    "data": {
                        "label": "Order Service",
                        "image": "Amazon-Elastic-Container-Service.svg",
                        "description": "Processes and manages user orders"
                    },
                    "position": {"x": 100, "y": 500}
                },
                {
                    "id": "payment_service",
                    "type": "custom",
                    "data": {
                        "label": "Payment Service",
                        "image": "AWS-Payment-Cryptography.svg",
                        "description": "Handles payment processing and integration"
                    },
                    "position": {"x": 250, "y": 500}
                },
                {
                    "id": "notification_service",
                    "type": "custom",
                    "data": {
                        "label": "Notification Service",
                        "image": "Amazon-Simple-Notification-Service.svg",
                        "description": "Sends notifications to users (email, SMS, push)"
                    },
                    "position": {"x": 400, "y": 500}
                },
                {
                    "id": "recommendation_service",
                    "type": "custom",
                    "data": {
                        "label": "Recommendation Service",
                        "image": "Amazon-SageMaker.svg",
                        "description": "Provides product recommendations"
                    },
                    "position": {"x": 550, "y": 500}
                },
                {
                    "id": "primary_db",
                    "type": "custom",
                    "data": {
                        "label": "Primary Database",
                        "image": "Amazon-RDS.svg",
                        "description": "Stores core application data (users, products, orders)"
                    },
                    "position": {"x": 175, "y": 600}
                },
                {
                    "id": "cache_db",
                    "type": "custom",
                    "data": {
                        "label": "Cache (Redis)",
                        "image": "Amazon-ElastiCache.svg",
                        "description": "Caches frequently accessed data for performance"
                    },
                    "position": {"x": 350, "y": 600}
                },
                {
                    "id": "analytics_db",
                    "type": "custom",
                    "data": {
                        "label": "Analytics Database",
                        "image": "Amazon-Redshift.svg",
                        "description": "Stores data for analytics and reporting"
                    },
                    "position": {"x": 525, "y": 600}
                },
                {
                    "id": "ci_cd",
                    "type": "custom",
                    "data": {
                        "label": "CI/CD Pipeline",
                        "image": "AWS-CodePipeline.svg",
                        "description": "Automates the build, test, and deployment process"
                    },
                    "position": {"x": 700, "y": 250}
                },
                {
                    "id": "monitoring",
                    "type": "custom",
                    "data": {
                        "label": "Monitoring (CloudWatch)",
                        "image": "Amazon-CloudWatch.svg",
                        "description": "Monitors application performance and health"
                    },
                    "position": {"x": 700, "y": 400}
                },
                {
                    "id": "security",
                    "type": "custom",
                    "data": {
                        "label": "Security (WAF)",
                        "image": "AWS-WAF.svg",
                        "description": "Web Application Firewall to protect against attacks"
                    },
                    "position": {"x": 700, "y": 500}
                },
                {
                    "id": "external_payment",
                    "type": "custom",
                    "data": {
                        "label": "External Payment Gateway",
                        "image": "connection.png",
                        "description": "Third-party payment processor (e.g., Stripe, PayPal)"
                    },
                    "position": {"x": 400, "y": 650}
                }
            ],
            "edges": [
                {"id": "edge_1", "type": "default", "label": "API Request", "source": "frontend_react", "target": "api_gateway"},
                {"id": "edge_2", "type": "default", "label": "API Request", "source": "frontend_mobile", "target": "api_gateway"},
                {"id": "edge_3", "type": "default", "label": "Route", "source": "api_gateway", "target": "load_balancer"},
                {"id": "edge_4", "type": "default", "label": "Route", "source": "load_balancer", "target": "user_service"},
                {"id": "edge_5", "type": "default", "label": "Route", "source": "load_balancer", "target": "auth_service"},
                {"id": "edge_6", "type": "default", "label": "Route", "source": "load_balancer", "target": "product_service"},
                {"id": "edge_7", "type": "default", "label": "Route", "source": "load_balancer", "target": "cart_service"},
                {"id": "edge_8", "type": "default", "label": "Route", "source": "load_balancer", "target": "order_service"},
                {"id": "edge_9", "type": "default", "label": "Route", "source": "load_balancer", "target": "payment_service"},
                {"id": "edge_10", "type": "default", "label": "Route", "source": "load_balancer", "target": "notification_service"},
                {"id": "edge_11", "type": "default", "label": "Route", "source": "load_balancer", "target": "recommendation_service"},
                {"id": "edge_12", "type": "default", "label": "Data Access", "source": "user_service", "target": "primary_db"},
                {"id": "edge_13", "type": "default", "label": "Data Access", "source": "auth_service", "target": "primary_db"},
                {"id": "edge_14", "type": "default", "label": "Data Access", "source": "product_service", "target": "primary_db"},
                {"id": "edge_15", "type": "default", "label": "Data Access", "source": "cart_service", "target": "cache_db"},
                {"id": "edge_16", "type": "default", "label": "Data Access", "source": "order_service", "target": "primary_db"},
                {"id": "edge_17", "type": "default", "label": "API Call", "source": "payment_service", "target": "external_payment"},
                {"id": "edge_18", "type": "default", "label": "Analytics", "source": "analytics_db", "target": "product_service"},
                {"id": "edge_19", "type": "default", "label": "Metrics", "source": "monitoring", "target": "api_gateway"},
                {"id": "edge_20", "type": "default", "label": "Metrics", "source": "monitoring", "target": "user_service"},
                {"id": "edge_21", "type": "default", "label": "Metrics", "source": "monitoring", "target": "auth_service"},
                {"id": "edge_22", "type": "default", "label": "Metrics", "source": "monitoring", "target": "product_service"},
                {"id": "edge_23", "type": "default", "label": "Metrics", "source": "monitoring", "target": "cart_service"},
                {"id": "edge_24", "type": "default", "label": "Metrics", "source": "monitoring", "target": "order_service"},
                {"id": "edge_25", "type": "default", "label": "Metrics", "source": "monitoring", "target": "payment_service"},
                {"id": "edge_26", "type": "default", "label": "Metrics", "source": "monitoring", "target": "notification_service"},
                {"id": "edge_27", "type": "default", "label": "Metrics", "source": "monitoring", "target": "recommendation_service"},
                {"id": "edge_28", "type": "default", "label": "Protection", "source": "security", "target": "api_gateway"}
            ],
            "metadata": {
                "domain": context.get("domain", "e-commerce"),
                "timestamp": datetime.utcnow().isoformat(),
                "edge_count": 28,
                "node_count": 19,
                "diagram_type": "architecture"
            }
        }
    
    def generate_database_diagram(self, description: str, context: Dict[str, Any], 
                                user_responses: Dict[str, str]) -> Dict[str, Any]:
        """Generate database schema diagram with React Flow compatible format"""
        print("i am hereeeee🦝")
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
        - metadata: object containing domain, timestamp, edge_count, node_count, and diagram_type.
        Important:
        - All table names must follow this naming convention: t_<table_name>
        Example: t_users, t_orders, t_project_tasks
        Each node (table) object must have the following structure:
        {{
            "id": "unique_table_id_lowercase_snake_case",
            "type": "custom",
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
            "type": "default",
            "label": "FK"
        }}

        Ensure that foreign key relationships are correctly represented by both:
        1. Setting "foreignKey": true and "references": "table_id.column_name" in the field definition of the child table.
        2. Creating an edge from the parent table's ID to the child table's ID (source -> target).
        3. Min 10 node should be created if the requirement is valid then normalize.

        Generate a comprehensive database schema with 20-50 related tables based on the project requirements.
        Position nodes in a logical layout with appropriate spacing (e.g., x: 0, 300, 600, 900 and y: 0, 150, 300, 450).

        Return ONLY valid JSON format with "nodes", "edges", and "metadata" sections, without markdown or code block formatting.
        The metadata section should include:
        {{
            "domain": "inferred_domain",
            "timestamp": "YYYY-MM-DDTHH:MM:SS.ssssss",
            "edge_count": number,
            "node_count": number,
            "diagram_type": "db_diagram"
        }}

        Now generate the database schema for:
        "{user_prompt}"
        """
        
        try:
            response = llm.invoke([HumanMessage(content=db_prompt)])
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                diagram = json.loads(json_match.group())
                if "metadata" not in diagram:
                    diagram["metadata"] = {
                        "domain": context.get("domain", "unknown"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "edge_count": len(diagram.get("edges", [])),
                        "node_count": len(diagram.get("nodes", [])),
                        "diagram_type": "db_diagram"
                    }
                return diagram
        except Exception as e:
            print(f"Database diagram error: {e}")
        
        return {
            "nodes": [
                {
                    "id": "users",
                    "type": "custom",
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
                    "type": "custom",
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
                    "type": "default",
                    "label": "FK"
                }
            ],
            "metadata": {
                "domain": context.get("domain", "unknown"),
                "timestamp": datetime.utcnow().isoformat(),
                "edge_count": 1,
                "node_count": 2,
                "diagram_type": "db_diagram"
            }
        }