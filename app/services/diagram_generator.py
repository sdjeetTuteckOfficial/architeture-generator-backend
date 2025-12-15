import json
import re
import traceback  # Added for detailed error logs
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import os
from datetime import datetime

# Try to import json_repair for robust parsing
try:
    import json_repair
except ImportError:
    json_repair = None
    print("Warning: 'json_repair' library not found. Install it with `pip install json_repair` for better stability.")

from constants.constants import AWS_AVAILABLE_IMAGES, AZURE_AVAILABLE_IMAGES, local_images

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# Use standard flash model (not lite) to avoid daily quota limits
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", 
    temperature=0.2, 
    max_tokens=8000
)

AVAILABLE_ICONS = AWS_AVAILABLE_IMAGES + AZURE_AVAILABLE_IMAGES + local_images

class DiagramGenerator:
    """Generate ReactFlow diagrams for different architecture types"""

    def _clean_and_parse_json(self, content: str) -> Dict[str, Any]:
        """
        Nuclear option for JSON parsing.
        """
        original_content = content  # Keep for debugging

        # 1. Strip Markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        content = content.strip()

        # 2. Try json_repair (Best Solution)
        if json_repair:
            try:
                return json_repair.loads(content)
            except Exception as e:
                print(f"⚠️ [DEBUG] json_repair failed: {e}")

        # 3. Manual Fixes (Fallback)
        try:
            # Fix: Missing comma between objects ie: } {  ->  }, {
            content = re.sub(r'}\s*{', '}, {', content)
            
            # Fix: Trailing commas ie: , ]  ->  ]
            content = re.sub(r',\s*([\]}])', r'\1', content)
            
            return json.loads(content)
        except Exception as e:
            print(f"❌ [DEBUG] Manual JSON Parsing Error: {e}")
            print(f"❌ [DEBUG] Failed JSON Content (First 500 chars): {content[:500]}...")
            
            # Last resort: Try to find the largest valid JSON object subset
            try:
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    print("⚠️ [DEBUG] Regex found JSON subset, attempting parse...")
                    return json.loads(match.group())
            except:
                pass
            return None

    def generate_architecture_diagram(self, description: str, context: Dict[str, Any], 
                                    user_responses: Dict[str, str]) -> Dict[str, Any]:
        """Generate comprehensive architecture diagram"""
        
        architecture_prompt = f"""
        ROLE: You are a strict JSON generator for a Software Architecture tool.
        
        INPUT DATA:
        - Description: {description}
        - Context: {json.dumps(context)}
        - User Responses: {json.dumps(user_responses)}
        
        TASK:
        Generate a JSON object representing a microservices architecture.
        
        CONSTRAINTS:
        1. **STRICT JSON ONLY**: Do not output markdown, comments, or explanations.
        2. **Node Limit**: Generate 10-20 essential nodes (Frontend, API, Services, DB).
        3. **Icons**: Use ONLY these filenames: {json.dumps(AVAILABLE_ICONS)}
        4. **Layout**:
           - Frontend: y=0
           - API Gateway: y=200
           - Services: y=400
           - Databases: y=600
        
        OUTPUT STRUCTURE (Must match exactly):
        {{
            "nodes": [
                {{
                    "id": "unique_id_str",
                    "type": "custom", 
                    "data": {{ 
                        "label": "Short Label",
                        "image": "icon_filename.svg",
                        "description": "Short desc"
                    }},
                    "position": {{ "x": 0, "y": 0 }}
                }}
            ],
            "edges": [
                {{
                    "id": "e1",
                    "source": "source_id", 
                    "target": "target_id",
                    "type": "default",
                    "label": "calls"
                }}
            ],
            "metadata": {{
                "domain": "inferred",
                "timestamp": "ISO_DATE",
                "diagram_type": "architecture"
            }}
        }}
        """
        
        try:
            response = llm.invoke([HumanMessage(content=architecture_prompt)])
            diagram = self._clean_and_parse_json(response.content)
            
            if diagram:
                if "metadata" not in diagram:
                    diagram["metadata"] = {}
                
                diagram["metadata"].update({
                    "domain": context.get("domain", "unknown"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "edge_count": len(diagram.get("edges", [])),
                    "node_count": len(diagram.get("nodes", [])),
                    "diagram_type": "architecture"
                })
                return diagram
            else:
                raise ValueError("JSON parsing returned None")

        except Exception as e:
            print(f"❌ [DEBUG] Architecture Gen Error: {e}")
            return self._get_fallback_architecture()

    def generate_database_diagram(self, description: str, context: Dict[str, Any], 
                                user_responses: Dict[str, str]) -> Dict[str, Any]:
        """Generate database schema diagram with React Flow compatible format"""
        print("\n🔍 [DEBUG] Starting Database Diagram Generation...")
        
        simplified_context = {
            "domain": context.get("domain", "General"),
            "core_requirement": description[:500]
        }

        db_prompt = f"""
        ROLE: Database Architect.
        TASK: Generate a React Flow JSON for an Entity Relationship Diagram (ERD).
        
        INPUT CONTEXT: {json.dumps(simplified_context)}
        USER REQUIREMENTS: {json.dumps(user_responses)}
        
        STRICT RULES:
        1. Output ONLY valid JSON. No Markdown code blocks (no ```json).
        2. Create 5-10 normalized tables.
        3. Table IDs MUST start with 't_' (e.g., t_users, t_orders).
        4. Define Foreign Keys in the 'fields' list (as 'foreignKey': true) AND in the 'edges' list.
        
        REQUIRED JSON STRUCTURE:
        {{
            "nodes": [
                {{
                    "id": "t_users",
                    "type": "custom",
                    "data": {{
                        "label": "Users",
                        "fields": [
                            {{ "name": "id", "type": "SERIAL", "primaryKey": true, "foreignKey": false }},
                            {{ "name": "email", "type": "VARCHAR(255)", "primaryKey": false, "foreignKey": false }}
                        ]
                    }},
                    "position": {{ "x": 0, "y": 0 }}
                }}
            ],
            "edges": [
                {{ "id": "e1", "source": "t_users", "target": "t_orders", "type": "default", "label": "1:N" }}
            ],
            "metadata": {{ "diagram_type": "db_diagram" }}
        }}
        """
        
        try:
            print("⏳ [DEBUG] Invoking LLM...")
            response = llm.invoke([HumanMessage(content=db_prompt)])
            
            # --- DEBUG LOGGING START ---
            print("\n---------------- RAW LLM RESPONSE ----------------")
            print(response.content)
            print("--------------------------------------------------\n")
            # --- DEBUG LOGGING END ---

            diagram = self._clean_and_parse_json(response.content)
            
            if not diagram:
                print("❌ [DEBUG] JSON Parser returned None. The LLM output might be empty or severely malformed.")
                raise ValueError("JSON parser returned None")
                
            if "nodes" not in diagram:
                if isinstance(diagram, list):
                    print("⚠️ [DEBUG] LLM returned a List instead of a Dict. Auto-correcting...")
                    diagram = {"nodes": diagram, "edges": [], "metadata": {}}
                else:
                    print(f"❌ [DEBUG] JSON is valid but missing 'nodes' key. Keys found: {diagram.keys()}")
                    raise ValueError("Parsed JSON missing 'nodes' key")

            if "metadata" not in diagram:
                diagram["metadata"] = {}
            
            diagram["metadata"].update({
                "domain": context.get("domain", "unknown"),
                "timestamp": datetime.utcnow().isoformat(),
                "node_count": len(diagram.get("nodes", [])),
                "edge_count": len(diagram.get("edges", [])),
                "diagram_type": "db_diagram"
            })
            
            print(f"✅ [DEBUG] Database Diagram Successfully Generated ({len(diagram['nodes'])} nodes)")
            return diagram

        except Exception as e:
            print(f"\n❌ [DEBUG] CRITICAL ERROR in Database Gen: {str(e)}")
            print("👇 [DEBUG] Full Traceback:")
            traceback.print_exc()
            return self._get_fallback_database()

    def _get_fallback_architecture(self):
        print("⚠️ [DEBUG] Triggering Architecture Fallback")
        return {
            "nodes": [
                {"id": "error_node", "type": "custom", "data": {"label": "Error Generating Diagram", "image": "alert.png", "description": "Please try again."}, "position": {"x": 250, "y": 250}}
            ],
            "edges": [],
            "metadata": {"diagram_type": "architecture", "error": "true"}
        }

    def _get_fallback_database(self):
        print("⚠️ [DEBUG] Triggering Database Fallback")
        return {
            "nodes": [
                {"id": "t_error", "type": "custom", "data": {"label": "Error", "fields": []}, "position": {"x": 100, "y": 100}}
            ],
            "edges": [],
            "metadata": {"diagram_type": "db_diagram", "error": "true"}
        }